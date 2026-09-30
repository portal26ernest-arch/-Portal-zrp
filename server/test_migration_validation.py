"""Stage 4B offline contract tests. No PostgreSQL or deployment database is used."""
import json
import sqlite3
import unittest
from pathlib import Path

from migration_validation import (ValidationError, compare, compare_migration_history,
                                  reconcile_linked_work_money, snapshot,
                                  validate_postgresql_schema)
from production_repository import Repository
from production_migrations import migrate_retention


def fixture():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE employees (telegram_id INTEGER, company_id INTEGER, full_name TEXT);
        CREATE TABLE portal_production (company_id INTEGER, kind TEXT, id TEXT,
            payload TEXT, created_at TEXT, PRIMARY KEY(company_id,kind,id));
        CREATE TABLE portal_production_migrations (company_id INTEGER, version INTEGER,
            applied_at TEXT, PRIMARY KEY(company_id,version));
        CREATE TABLE app_users (id INTEGER, company_id INTEGER, username TEXT,
            pin_hash TEXT, role TEXT);
        CREATE TABLE portal_clients (id INTEGER, company_id INTEGER, name TEXT);
        CREATE TABLE portal_client_operations (id INTEGER, company_id INTEGER,
            client_id INTEGER, employee_rate REAL, client_rate REAL);
        CREATE TABLE work_log (id INTEGER, company_id INTEGER, quantity INTEGER,
            salary REAL, revenue REAL);
        CREATE TABLE client_invoices (id INTEGER, company_id INTEGER, amount_due REAL);
        CREATE TABLE client_payments (id INTEGER, company_id INTEGER, amount REAL);
    ''')
    for company_id in (1, 2):
        conn.execute('INSERT INTO employees VALUES (?,?,?)',
                     (100 + company_id, company_id, 'Worker'))
        conn.execute('INSERT INTO portal_production_migrations VALUES (?,?,?)',
                     (company_id, 3, '2026-09-25'))
        conn.execute('INSERT INTO app_users VALUES (?,?,?,?,?)',
                     (company_id, company_id, 'worker', 'secret-hash-canary', 'packer'))
        conn.execute('INSERT INTO portal_clients VALUES (?,?,?)',
                     (company_id, company_id, 'Client'))
        conn.execute('INSERT INTO portal_client_operations VALUES (?,?,?,?,?)',
                     (company_id, company_id, company_id, 2.0, 5.0))
        conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)',
                     (company_id, company_id, 2, 4.0, 10.0))
        conn.execute('INSERT INTO client_invoices VALUES (?,?,?)',
                     (company_id, company_id, 10.0))
        conn.execute('INSERT INTO client_payments VALUES (?,?,?)',
                     (company_id, company_id, 3.0))
        for kind, payload in (
            ('batches', {'number': 'PRT-2026-' + str(company_id)}),
            ('tasks', {'batch_id': 'batch'}),
            ('tariffs', {'employee_rate': 200, 'client_rate': 500, 'effective_from': '2026-09-25'}),
            ('works', {'salary': 400, 'revenue': 1000, 'quantity': 2}),
            ('permissions', {'overrides': {'work.write': True}}),
            ('plans', {'salary': 400, 'revenue': 1000}),
            ('invoices', {'amount': 1000}),
            ('payments', {'amount': 300}),
            ('access_events', {'result': 'success'}),
            ('work_timers', {'net_seconds': 1800}),
        ):
            identity = kind + str(company_id)
            data = dict(payload, id=identity, company_id=company_id)
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (company_id, kind, identity, json.dumps(data), '2026-09-25'))
    conn.commit()
    return conn


class MigrationValidationTest(unittest.TestCase):
    def test_linked_legacy_money_reconciles_in_company_scope_without_writes(self):
        conn = fixture()
        try:
            conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)',
                         (101, 1, 2, 10.01, 20.03))
            conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)',
                         (101, 2, 2, 99.99, 199.98))
            for company_id, salary, revenue in ((1, 1001, 2003), (2, 9999, 19998)):
                payload = dict(id='linked-' + str(company_id), company_id=company_id,
                               legacy_id=101, salary=salary, revenue=revenue)
                conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                             (company_id, 'works', payload['id'], json.dumps(payload),
                              '2026-09-30'))
            before = conn.execute(
                'SELECT company_id,id,salary,revenue FROM work_log WHERE id=101 ORDER BY company_id'
            ).fetchall()
            self.assertEqual(reconcile_linked_work_money(conn, conn, 1),
                             {'matched_work_count': 1,
                              'unlinked_legacy_work_count': 1,
                              'money_fields_checked': 2})
            after = conn.execute(
                'SELECT company_id,id,salary,revenue FROM work_log WHERE id=101 ORDER BY company_id'
            ).fetchall()
            self.assertEqual(before, after)
        finally:
            conn.close()

    def test_linked_legacy_money_uses_half_up_minor_unit_rounding_and_fails_closed(self):
        conn = fixture()
        try:
            conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)', (77, 1, 1, 1.005, None))
            payload = dict(id='rounding-case', company_id=1, legacy_id=77,
                           salary=101, revenue=None)
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (1, 'works', payload['id'], json.dumps(payload), '2026-09-30'))
            self.assertEqual(reconcile_linked_work_money(conn, conn, 1),
                             {'matched_work_count': 1,
                              'unlinked_legacy_work_count': 1,
                              'money_fields_checked': 1})
            payload['salary'] = 102
            conn.execute('UPDATE portal_production SET payload=? WHERE company_id=1 AND kind=? AND id=?',
                         (json.dumps(payload), 'works', payload['id']))
            with self.assertRaisesRegex(ValidationError, 'salary'):
                reconcile_linked_work_money(conn, conn, 1)
        finally:
            conn.close()

    def test_linked_legacy_direct_cost_reconciles_to_canonical_usage(self):
        conn = fixture()
        try:
            conn.execute('ALTER TABLE work_log ADD COLUMN direct_cost REAL')
            conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?,?)',
                         (88, 1, 1, 2.50, 5.00, 3.75))
            work = dict(id='canonical-work-88', company_id=1, legacy_id=88,
                        salary=250, revenue=500)
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (1, 'works', work['id'], json.dumps(work), '2026-09-30'))
            usage = dict(id='usage-88', company_id=1, work_id=work['id'], cost=375, source='norm')
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (1, 'usage', usage['id'], json.dumps(usage), '2026-09-30'))
            additional = dict(id='additional-usage-88', company_id=1,
                              work_id=work['id'], cost=237, source='additional_actual')
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (1, 'usage', additional['id'], json.dumps(additional), '2026-09-30'))
            self.assertEqual(reconcile_linked_work_money(conn, conn, 1),
                             {'matched_work_count': 1,
                              'unlinked_legacy_work_count': 1,
                              'money_fields_checked': 3})
            usage['cost'] = 374
            conn.execute('UPDATE portal_production SET payload=? WHERE company_id=1 AND kind=? AND id=?',
                         (json.dumps(usage), 'usage', usage['id']))
            with self.assertRaisesRegex(ValidationError, 'direct_cost'):
                reconcile_linked_work_money(conn, conn, 1)
        finally:
            conn.close()

    def test_linked_money_filter_targets_one_work_without_hiding_full_scan_duplicates(self):
        conn = fixture()
        try:
            conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)',
                         (89, 1, 1, 2.50, 5.00))
            for identity in ('work-89-a', 'work-89-b'):
                payload = dict(id=identity, company_id=1, legacy_id=89,
                               salary=250, revenue=500)
                conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                             (1, 'works', identity, json.dumps(payload), '2026-09-30'))
            with self.assertRaisesRegex(ValidationError, 'Duplicate canonical link'):
                reconcile_linked_work_money(conn, conn, 1)
            self.assertEqual(reconcile_linked_work_money(
                conn, conn, 1, canonical_work_ids=('work-89-a',)),
                {'matched_work_count': 1,
                 'unlinked_legacy_work_count': 1,
                 'money_fields_checked': 2})
        finally:
            conn.close()

    def test_postgresql_sql_adapter_contract_without_server(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

        class PostgreSQLShape:
            def __init__(self, sqlite_connection):
                self.sqlite_connection = sqlite_connection
                self.queries = []

            def execute(self, query, args=()):
                self.queries.append((query, args))
                if query.startswith('SELECT set_config'):
                    return Rows([])
                if 'information_schema.columns' in query:
                    table = args[0]
                    return Rows([(r[1],) for r in self.sqlite_connection.execute(
                        'PRAGMA table_info(' + table + ')')])
                return self.sqlite_connection.execute(query.replace('%s', '?'), args)

        conn = fixture()
        try:
            shaped = PostgreSQLShape(conn)
            repo = Repository(shaped, 1, 'postgresql')
            self.assertEqual(repo.get('works', 'works1')['salary'], 400)
            self.assertTrue(compare(snapshot(conn, 'sqlite', 1),
                                    snapshot(shaped, 'postgresql', 1)))
            self.assertTrue(any('company_id=%s' in query for query, _ in shaped.queries))
            self.assertEqual(shaped.queries[0][1], ('1',))
        finally:
            conn.close()

    def test_schema_contract_and_company_scoped_snapshot(self):
        sql = (Path(__file__).parent / 'migrations' / 'postgresql_stage3.sql').read_text(encoding='utf-8')
        self.assertTrue(validate_postgresql_schema(sql))
        self.assertIn("OLD.kind IN ('chat_messages','chat_pins','chat_attachments')",sql)
        self.assertIn("RAISE EXCEPTION 'production history is immutable'",sql)
        retention=(Path(__file__).parent/'migrations'/'postgresql_stage5_chat_retention.sql').read_text(encoding='utf-8')
        self.assertIn("OLD.kind IN ('chat_messages','chat_pins','chat_attachments')",retention)
        self.assertIn("ON CONFLICT (company_id,version) DO NOTHING",retention)
        self.assertNotRegex(retention,r'(?i)\b(?:DROP TABLE|TRUNCATE|ALTER POLICY|CREATE POLICY)\b')
        rls=(Path(__file__).parent/'migrations'/'postgresql_rls_context.sql').read_text(encoding='utf-8')
        self.assertIn("(cid,5,CURRENT_TIMESTAMP::text)",rls)
        conn = fixture()
        try:
            one, two = snapshot(conn, 'sqlite', 1), snapshot(conn, 'sqlite', 2)
            self.assertEqual(one['portal_production']['count'], 10)
            self.assertNotEqual(one['portal_production']['sha256'], two['portal_production']['sha256'])
            self.assertTrue(compare(one, snapshot(conn, 'sqlite', 1)))
            self.assertNotIn('secret-hash-canary', json.dumps(one))
        finally:
            conn.close()

    def test_historical_and_control_changes_fail_validation(self):
        changes = (
            "UPDATE portal_production SET payload=replace(payload,'400','401') WHERE kind='works' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'200','201') WHERE kind='tariffs' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1800','1801') WHERE kind='work_timers' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'true','false') WHERE kind='permissions' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1000','1001') WHERE kind='plans' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1000','1001') WHERE kind='invoices' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'300','301') WHERE kind='payments' AND company_id=1",
            'UPDATE work_log SET salary=4.01 WHERE company_id=1',
            'UPDATE client_payments SET amount=3.01 WHERE company_id=1',
            'DELETE FROM portal_production WHERE kind=\'tasks\' AND company_id=1',
        )
        for change in changes:
            with self.subTest(change=change):
                conn = fixture()
                try:
                    before = snapshot(conn, 'sqlite', 1)
                    conn.execute(change)
                    with self.assertRaises(ValidationError):
                        compare(before, snapshot(conn, 'sqlite', 1))
                finally:
                    conn.close()

    def test_cutover_migration_history_allows_only_stage6_marker(self):
        source = [(3, '2026-09-25'), (4, '2026-09-25'), (5, '2026-09-25')]
        self.assertTrue(compare_migration_history(
            source, source + [(6, '2026-09-27')], required_version=6))
        self.assertTrue(compare_migration_history(
            source + [(6, '2026-09-25')], source + [(6, '2026-09-25')],
            required_version=6))
        bad_histories = (
            source,
            [(3, 'changed'), (4, '2026-09-25'), (5, '2026-09-25'), (6, '2026-09-27')],
            source + [(6, '2026-09-27'), (7, 'unexpected')],
            source + [(6, '')],
            source + [(6, '2026-09-27'), (6, 'duplicate')],
        )
        for destination in bad_histories:
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValidationError, 'portal_production_migrations'):
                    compare_migration_history(source, destination, required_version=6)

    def test_missing_company_id_and_ledger_identity_are_rejected(self):
        conn = fixture()
        try:
            conn.execute("UPDATE portal_production SET payload='{}' WHERE company_id=1 AND kind='batches'")
            with self.assertRaisesRegex(ValidationError, 'Ledger identity'):
                snapshot(conn, 'sqlite', 1)
        finally:
            conn.close()
        conn = fixture()
        try:
            conn.execute('ALTER TABLE work_log RENAME TO old_work_log')
            conn.execute('CREATE TABLE work_log (id INTEGER, salary REAL)')
            with self.assertRaisesRegex(ValidationError, 'company_id'):
                snapshot(conn, 'sqlite', 1)
        finally:
            conn.close()

    def test_missing_table_or_schema_difference_fails_closed(self):
        conn = fixture()
        try:
            expected = snapshot(conn, 'sqlite', 1)
            conn.execute('DROP TABLE client_payments')
            with self.assertRaises(ValidationError):
                compare(expected, snapshot(conn, 'sqlite', 1))
        finally:
            conn.close()


class RetentionMigrationTest(unittest.TestCase):
    class Result:
        def __init__(self, row=None):
            self.row=row
        def fetchone(self):
            return self.row

    class Repo:
        dialect='postgresql'
        company_id=1
        def __init__(self, definition):
            self.definition=definition
            self.inserted=False
        def sql(self, query, args=()):
            if 'SELECT 1 FROM portal_production_migrations' in query:
                return RetentionMigrationTest.Result(None)
            if 'pg_get_functiondef' in query:
                return RetentionMigrationTest.Result((self.definition,))
            if 'INSERT INTO portal_production_migrations' in query:
                self.inserted=True
                return RetentionMigrationTest.Result(None)
            raise AssertionError(query)

    def test_postgresql_retention_marker_requires_verified_schema(self):
        old=self.Repo("RAISE EXCEPTION 'production history is immutable'")
        with self.assertRaisesRegex(RuntimeError,'chat retention migration'):
            migrate_retention(old)
        self.assertFalse(old.inserted)

        current=self.Repo(
            "chat_messages chat_pins chat_attachments "
            "RAISE EXCEPTION 'production history is immutable'"
        )
        migrate_retention(current)
        self.assertTrue(current.inserted)


if __name__ == '__main__':
    unittest.main()
