import unittest
import sqlite3
from datetime import datetime, timezone

from reminder_jobs import (Reminder, ReminderRunner, persist_once, source_candidates,
                           run_scheduled_company, run_configured_company, next_run_at)
from production_repository import Repository


class FixtureRepository:
    company_id=8
    def __init__(self,rows):self.rows=rows
    def list(self,kind):return list(self.rows.get(kind,[]))


class ReminderRunnerTests(unittest.TestCase):
    def test_disabled_by_default_never_calls_delivery(self):
        called = []
        result = ReminderRunner().run(
            4, [Reminder("invoice_overdue", "inv-1", "Invoice overdue")],
            dispatch_once=lambda *args: called.append(args) or True,
        )
        self.assertEqual(result, {"enabled": False, "sent": 0, "duplicate": 0, "failed": 0})
        self.assertEqual(called, [])

    def test_company_scoped_idempotency_and_retry_after_failure(self):
        now = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
        runner = ReminderRunner(enabled=True, cadence="daily", clock=lambda: now)
        sent = set()
        deliveries = []
        reminder = Reminder("invoice_overdue", "invoice-7", "Overdue")

        def dispatch_once(company, candidate, key):
            if (company, key) in sent:
                return False
            if not deliveries:
                deliveries.append((company, key, "failed"))
                raise RuntimeError("must not be exposed")
            deliveries.append((company, key, "sent"))
            sent.add((company, key))
            return True

        failed = runner.run(4, [reminder], dispatch_once=dispatch_once)
        retried = runner.run(4, [reminder], dispatch_once=dispatch_once)
        repeated = runner.run(4, [reminder], dispatch_once=dispatch_once)
        other_company = runner.run(5, [reminder], dispatch_once=dispatch_once)

        self.assertEqual(failed["failed"], 1)
        self.assertEqual(retried["sent"], 1)
        self.assertEqual(repeated["duplicate"], 1)
        self.assertEqual(other_company["sent"], 1)
        self.assertEqual(deliveries[0][1], deliveries[1][1])
        self.assertEqual(deliveries[1][1], deliveries[2][1])
        self.assertEqual(deliveries[1][0], 4)
        self.assertEqual(deliveries[2][0], 5)

    def test_weekly_cadence_and_timezone_boundaries(self):
        runner = ReminderRunner(enabled=True, cadence="weekly")
        monday = datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(runner.cadence_id(monday), "2026-W40")
        self.assertEqual(runner.cadence_id(datetime(2026, 10, 4, 23, 59, tzinfo=timezone.utc)), "2026-W40")
        moscow = ReminderRunner(enabled=True, cadence="daily", utc_offset_minutes=180)
        self.assertEqual(moscow.cadence_id(datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)), "2026-10-01")
        with self.assertRaises(ValueError):
            runner.cadence_id(datetime(2026, 9, 30))

    def test_missing_or_invalid_company_scope_fails_closed(self):
        runner = ReminderRunner(enabled=True)
        for company in (None, 0, "4", True):
            with self.subTest(company=company), self.assertRaises(PermissionError):
                runner.run(company, [], dispatch_once=lambda *_: True)
        with self.assertRaises(ValueError):
            ReminderRunner(utc_offset_minutes=900)
        connection=sqlite3.connect(':memory:')
        try:
            connection.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(company_id,kind,id))')
            with self.assertRaises(ValueError):run_scheduled_company(Repository(connection,8),enabled='yes')
        finally:connection.close()

    def test_candidate_identity_rejects_control_and_secret_like_values(self):
        with self.assertRaises(ValueError):
            Reminder("invoice", "../private-token", "x").key("2026-09-30")

    def test_candidates_use_partial_invoice_balance_local_due_date_and_unbilled_work(self):
        repo=FixtureRepository({
            'invoices':[
                {'id':'late-partial','amount':1000,'due_at':'2026-09-29','work_ids':['billed-work']},
                {'id':'paid','amount':500,'due_at':'2026-09-28','work_ids':['paid-work']},
                {'id':'due-today','amount':700,'due_at':'2026-10-01','work_ids':['today-work']},
                {'id':'due-at-local-day-end','amount':300,'due_at':'2026-09-30T22:30:00+00:00','work_ids':[]},
            ],
            'payments':[{'invoice_id':'late-partial','amount':400},{'invoice_id':'paid','amount':500}],
            'invoice_revisions':[],
            'works':[{'id':'billed-work'},{'id':'paid-work'},{'id':'today-work'},{'id':'unbilled-work'}],
        })
        candidates=source_candidates(repo,datetime(2026,9,30,22,tzinfo=timezone.utc),utc_offset_minutes=180)
        self.assertEqual([(c.kind,c.entity_id) for c in candidates],[('invoice_overdue','late-partial'),('work_unbilled','unbilled-work')])

    def test_notification_sink_is_atomic_company_scoped_and_idempotent(self):
        connection=sqlite3.connect(':memory:')
        try:
            connection.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(company_id,kind,id))')
            repository=Repository(connection,8)
            reminder=Reminder('invoice_overdue','invoice-1','Просрочена оплата')
            key=reminder.key('2026-09-30');now=datetime(2026,9,30,tzinfo=timezone.utc)
            self.assertTrue(persist_once(repository,8,reminder,key,now))
            self.assertFalse(persist_once(repository,8,reminder,key,now))
            self.assertEqual(connection.execute("SELECT count(*) FROM portal_production WHERE company_id=8 AND kind='notifications'").fetchone()[0],1)
            with self.assertRaises(PermissionError):persist_once(repository,9,reminder,key,now)
        finally:connection.close()

    def test_operator_entrypoint_is_disabled_and_records_sanitized_run(self):
        connection=sqlite3.connect(':memory:')
        try:
            connection.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(company_id,kind,id))')
            repository=Repository(connection,8)
            repository.insert('works',{'client_id':1,'completed_at':'2026-09-29'},'work-1')
            now=datetime(2026,9,30,21,tzinfo=timezone.utc)
            disabled=run_scheduled_company(repository,now=now,run_id='disabled-1')
            self.assertEqual(disabled['outcome'],'disabled')
            self.assertEqual(disabled['candidate_count'],0)
            self.assertEqual(repository.list('notifications'),[])
            enabled=run_scheduled_company(repository,enabled=True,now=now,run_id='enabled-1')
            self.assertEqual((enabled['outcome'],enabled['sent'],enabled['failed']),('success',1,0))
            self.assertEqual(enabled['next_run_at'],'2026-10-01T00:00:00+00:00')
            run_rows=repository.list('reminder_job_runs')
            self.assertEqual({row['run_id'] for row in run_rows},{'disabled-1','enabled-1'})
            self.assertNotIn('company_id',enabled)
            self.assertNotIn('secret',str(run_rows).lower())
        finally:connection.close()

    def test_daily_weekly_next_run_boundaries(self):
        now=datetime(2026,9,30,21,30,tzinfo=timezone.utc)
        self.assertEqual(next_run_at(now,'daily',180),'2026-10-01T21:00:00+00:00')
        self.assertEqual(next_run_at(now,'weekly',180),'2026-10-04T21:00:00+00:00')
        with self.assertRaises(ValueError):next_run_at(now,'daily',True)

    def test_operator_retry_records_generic_failure_then_success(self):
        connection=sqlite3.connect(':memory:')
        try:
            connection.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(company_id,kind,id))')
            repository=Repository(connection,8)
            repository.insert('works',{'client_id':1},'work-retry')
            original=repository.insert_once
            failed_once=[]
            def flaky(kind,data,identity):
                if kind=='notifications' and not failed_once:
                    failed_once.append(True)
                    raise RuntimeError('private backend detail must not be stored')
                return original(kind,data,identity)
            repository.insert_once=flaky
            now=datetime(2026,9,30,21,tzinfo=timezone.utc)
            first=run_scheduled_company(repository,enabled=True,now=now,run_id='retry-run-1')
            second=run_scheduled_company(repository,enabled=True,now=now,run_id='retry-run-2')
            self.assertEqual(first['outcome'],'retryable')
            self.assertEqual((second['outcome'],second['sent']),('success',1))
            records=repository.list('reminder_job_runs')
            self.assertEqual({row['outcome'] for row in records},{'retryable','success'})
            self.assertNotIn('private backend detail',str(records))
        finally:connection.close()

    def test_saved_company_settings_drive_operator_run_but_default_disabled(self):
        connection=sqlite3.connect(':memory:')
        try:
            connection.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(company_id,kind,id))')
            repository=Repository(connection,8)
            repository.insert('works',{'client_id':1,'completed_at':'2026-09-29'},'configured-work')
            now=datetime(2026,9,30,21,tzinfo=timezone.utc)
            disabled=run_configured_company(repository,now=now,run_id='configured-disabled')
            self.assertEqual((disabled['enabled'],disabled['outcome'],disabled['candidate_count']),(False,'disabled',0))
            self.assertEqual(repository.list('notifications'),[])
            repository.insert('settings',{'reminder_enabled':False,'reminder_cadence':'daily',
                'utc_offset_minutes':180},'control')
            settings=repository.get('settings','control')
            settings.update(reminder_enabled=True,reminder_cadence='weekly')
            repository.update('settings',settings)
            enabled=run_configured_company(repository,now=now,run_id='configured-enabled')
            self.assertEqual((enabled['outcome'],enabled['cadence'],enabled['cadence_id']),
                ('success','weekly','2026-W40'))
            self.assertTrue(enabled['enabled'])
            self.assertEqual(enabled['sent'],1)
            self.assertNotIn('company_id',enabled)
            self.assertEqual(len(repository.list('notifications')),1)
            other_company=Repository(connection,9)
            isolated=run_configured_company(other_company,now=now,run_id='foreign-settings')
            self.assertEqual((isolated['outcome'],isolated['sent']),('disabled',0))
            self.assertEqual(other_company.list('notifications'),[])
        finally:connection.close()


if __name__ == "__main__":
    unittest.main()
