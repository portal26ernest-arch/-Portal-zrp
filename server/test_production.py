"""Production API tests. Only temporary fixtures, never a deployment database."""
import json
import sqlite3
import unittest
import uuid
from datetime import datetime, timedelta
import test_portal_app_server as legacy
import test_portal_tenancy as isolation
from production_repository import Repository
from production_migrations import migrate
from production_service import Production

portal=legacy.portal

class ProductionTest(unittest.TestCase):
    request=legacy.PortalAPITest.request
    tearDown=legacy.PortalAPITest.tearDown
    role_token=isolation.CompanyIsolationTest.role_token

    def setUp(self):
        isolation.CompanyIsolationTest.setUp(self)
        for cid in (1,self.other):
            with portal.tenants.company_scope(cid),portal.db() as conn:migrate(conn,cid)

    def post(self,action,body,token=None,status=200):
        return self.request('/api/v3/'+action,token or self.admin,dict(body,request_id=body.get('request_id',str(uuid.uuid4()))),status=status)

    def get(self,action,token=None,status=200):return self.request('/api/v3/'+action,token or self.admin,status=status)

    def batch(self,**overrides):return self.post('batches',dict(client_id=1,product='Коробка',quantity=10,**overrides))['data']

    def task(self,batch):return self.post('tasks',dict(batch_id=batch['id'],operation_id=1,quantity=10,assignees=[self.worker_id]))['data']

    def work(self,**overrides):return self.post('work',dict(client_id=1,operation_id=1,quantity=2,**overrides),self.worker)['data']

    def test_batches_isolated_and_numbers_unique(self):
        a=self.batch();b=self.batch();other=self.post('batches',dict(client_id=1,product='Другое',quantity=10),self.other_admin)['data']
        self.assertEqual(len({a['number'],b['number'],other['number']}),3)
        self.assertTrue(a['number'].startswith('PRT-'))
        self.assertNotIn(other['id'],[x['id'] for x in self.get('batches')['data']])
        self.post('tasks',dict(batch_id=other['id'],operation_id=1,quantity=10,assignees=[self.worker_id]),status=400)
        self.post('batches',dict(client_id=1,product='X',quantity=1,company_id=self.other),status=403)
        self.get('batches?company_id=2',status=403)

    def test_task_work_assignment_remaining_and_completion(self):
        b=self.batch();t=self.task(b)
        w=self.work(task_id=t['id'])
        self.assertEqual(w['batch_id'],b['id']);self.assertEqual(w['salary'],400)
        self.assertNotIn('revenue',w)
        row=self.get('tasks',self.worker)['data'][0];self.assertEqual((row['done'],row['remaining']),(2,8))
        self.post('work',dict(task_id=t['id'],quantity=9),self.worker,status=400)
        other=portal.save_user(dict(username='second',pin='1234',role='packer',telegram_id=202))
        with portal.db() as conn:token=portal.create_session(conn,other)
        self.post('work',dict(task_id=t['id'],quantity=1),token,status=403)
        self.post('work',dict(task_id=t['id'],quantity=8),self.worker)
        self.assertTrue(self.get('batches')['data'][0]['ready'])
        self.post('shipments',dict(batch_id=b['id'],direction='FBO'))
        self.assertEqual(self.get('batches')['data'][0]['stage'],'shipped')

    def test_without_task_and_later_link_preserve_money(self):
        w=self.work();self.assertTrue(w['without_task']);self.assertIsNone(w['batch_id'])
        before=self.get('works')['data'][0];b=self.batch()
        self.post('links',dict(work_id=w['id'],batch_id=b['id']))
        after=self.get('works')['data'][0]
        self.assertEqual((before['salary'],before['revenue']),(after['salary'],after['revenue']))
        self.assertEqual(after['batch_id'],b['id'])
        self.post('links',dict(work_id=w['id'],batch_id=b['id']),status=400)

    def test_tariff_history_salary_revenue_and_future_dates(self):
        w=self.work();invoice=self.post('invoices',dict(work_ids=[w['id']]))['data']
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=3,client_rate=8))
        new=self.work()
        self.assertEqual(new['salary'],600)
        self.assertEqual(self.get('invoices')['data'][0]['amount'],invoice['amount'])
        old=self.get('works')['data'][0];self.assertEqual((old['salary'],old['revenue']),(400,1000))
        future=(datetime.utcnow()+timedelta(days=1)).isoformat()
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=99,effective_from=future))
        self.assertEqual(self.work()['salary'],600)
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=1,effective_from='2020-01-01'),status=400)

    def test_individual_grant_deny_and_legacy_bypass(self):
        self.post('permissions',dict(user_id=self.worker_id,permissions={'batches.receive':True,'work.write':False}))
        self.post('batches',dict(client_id=1,product='X',quantity=1),self.worker)
        self.post('work',dict(client_id=1,operation_id=1,quantity=1),self.worker,status=403)
        self.request('/api/work',self.worker,dict(client_id=1,operation_id=1,quantity=1),status=403)
        me=self.request('/api/me',self.worker)['user'];self.assertNotIn('work.write',me['permissions'])
        self.post('permissions',dict(user_id=self.worker_id,mode='reset'))
        self.work()

    def test_permissions_copy_and_no_platform_owner_or_escalation(self):
        self.post('permissions',dict(user_id=self.worker_id,permissions={'platform_owner':True}),status=400)
        self.post('permissions',dict(user_id=self.worker_id,permissions={'finance.read':True}),self.worker,status=403)
        self.request('/api/users/'+str(self.worker_id),self.admin,dict(role='platform_owner'),status=403)
        manager=self.role_token('manager')
        uid=self.request('/api/me',manager)['user']['id']
        self.post('permissions',dict(user_id=uid,permissions={'users.manage':True}))
        self.post('permissions',dict(user_id=self.worker_id,permissions={'finance.read':True}),manager,status=403)
        self.request('/api/users/'+str(self.admin_id),manager,dict(pin='5555'),status=403)
        self.post('permissions',dict(user_id=self.worker_id,mode='copy',source_id=uid))
        self.assertIn('users.manage',self.request('/api/me',self.worker)['user']['permissions'])

    def test_plan_fact_and_actual_materials(self):
        b=self.batch();t=self.task(b);w=self.work(task_id=t['id'])
        economy=self.get('economy?batch_id='+b['id'])['data']
        self.assertEqual(economy['plan']['salary'],2000);self.assertEqual(economy['plan']['materials'],4000)
        self.assertEqual(economy['fact']['salary'],400);self.assertEqual(economy['fact']['materials'],800)
        self.assertEqual(economy['fact']['profit'],-200)
        self.post('usage',dict(work_id=w['id'],material_id=1,quantity=1))
        self.post('expenses',dict(batch_id=b['id'],amount=1,category='Доставка'))
        e=self.get('economy?batch_id='+b['id'])['data'];self.assertEqual(e['fact']['profit'],-500)
        self.assertEqual(e['deviation']['materials'],-3000)
        finance=self.get('finance')['data']['clients'][0];self.assertEqual(finance['profit'],-500)
        self.get('finance',self.worker,status=403)

    def test_invoice_payment_chain_and_no_double_billing(self):
        w=self.work();attention=self.get('today')['data']['attention'];self.assertIn('not_invoiced',[a['type'] for a in attention])
        i=self.post('invoices',dict(work_ids=[w['id']],due_at='2020-01-01'))['data']
        self.post('invoices',dict(work_ids=[w['id']]),status=400)
        self.post('payments',dict(invoice_id=i['id'],amount=4))
        invoice=self.get('invoices')['data'][0];self.assertEqual((invoice['status'],invoice['remaining']),('partial',600))
        self.post('payments',dict(invoice_id=i['id'],amount=7),status=400)
        self.post('payments',dict(invoice_id=i['id'],amount=6));self.assertEqual(self.get('invoices')['data'][0]['status'],'paid')
        self.assertNotIn('not_invoiced',[a['type'] for a in self.get('today')['data']['attention']])

    def test_idempotency_and_transaction_rollback(self):
        body=dict(client_id=1,operation_id=1,quantity=2,request_id='retry-work')
        a=self.post('work',body,self.worker)['data'];b=self.post('work',body,self.worker)['data'];self.assertEqual(a['id'],b['id'])
        self.assertEqual(len(self.get('works')['data']),1)
        self.post('work',dict(body,quantity=3),self.worker,status=400)
        with portal.db() as conn:before=conn.execute('SELECT COUNT(*) FROM work_log').fetchone()[0]
        self.post('work',dict(client_id=1,operation_id=999,quantity=2),self.worker,status=400)
        with portal.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM work_log').fetchone()[0],before)

    def test_migration_repeat_preserves_old_rows_and_append_only(self):
        with portal.db() as conn:
            before=[tuple(r) for r in conn.execute('SELECT * FROM work_log')]
            migrate(conn,1)
            self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM work_log')])
        w=self.work()
        with portal.db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):conn.execute("DELETE FROM portal_production WHERE kind='works'")
        with portal.db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):conn.execute("UPDATE portal_production SET payload='{}' WHERE kind='tariffs'")

    def test_company_context_cannot_be_forged(self):
        self.request('/api/v3/today',self.worker,status=403,extra_headers={'X-Portal-Company':str(self.other)})
        foreign=self.post('work',dict(client_id=1,operation_id=1,quantity=1),self.other_worker)['data']
        self.post('invoices',dict(work_ids=[foreign['id']]),status=400)

    def test_analytics_self_only_and_missing_time_is_unknown(self):
        self.work();data=self.get('analytics',self.worker)['data']
        self.assertFalse(data['ranking']);self.assertIsNone(data['groups'][0]['units_per_hour'])
        self.assertEqual(data['groups'][0]['user_id'],self.worker_id)
        b=self.batch();t=self.task(b)
        self.post('work',dict(task_id=t['id'],quantity=2,started_at=(datetime.utcnow()-timedelta(hours=1)).isoformat()),self.worker)
        forecast=self.get('analytics',self.worker)['data']['forecasts'][0]
        self.assertGreater(forecast['units_per_hour'],0);self.assertIsNotNone(forecast['estimated_completion'])

    def test_multiple_operations_do_not_double_count_finished_units(self):
        b=self.batch();t=self.task(b);self.post('work',dict(task_id=t['id'],quantity=10),self.worker)
        op=portal.save_operation(dict(name='Проверка',employee_rate=1,client_rate=2),1)
        self.post('tasks',dict(batch_id=b['id'],operation_id=op,quantity=10,assignees=[self.worker_id]))
        progress=self.get('batches')['data'][0];self.assertEqual(progress['done'],0);self.assertFalse(progress['ready'])

    def test_control_schedule_and_uninvoiced_separate_from_debt(self):
        self.work();self.post('settings',dict(monday_time='11:00',wednesday_time='12:00',utc_offset_minutes=0))
        with portal.db() as conn:
            r=Repository(conn,1);u=next(u for u in r.catalog('users') if u['id']==self.admin_id)
            s=Production(r,u,lambda:'2026-09-30T13:00:00.000000')
            data=s.today();self.assertEqual(data['debt'],0);self.assertIn('not_invoiced',[a['type'] for a in data['attention']])
            self.assertEqual(s.settings()['wednesday_time'],'12:00')

    def test_legacy_catalog_tariff_changes_append_version(self):
        w=self.work();self.request('/api/admin/clients/1/operations/1',self.admin,dict(employee_rate=7))
        self.assertEqual(self.work()['salary'],1400)
        self.assertEqual(self.get('works')['data'][0]['salary'],400)

    def test_bad_quantity_and_invalid_assignments(self):
        for value in (True,0,-1,1.2,'2'):
            self.post('work',dict(client_id=1,operation_id=1,quantity=value),self.worker,status=400)
        b=self.batch();self.post('tasks',dict(batch_id=b['id'],operation_id=1,quantity=10,assignees=[999]),status=400)

    def test_finance_not_exposed_to_worker(self):
        w=self.work();self.assertNotIn('revenue',w)
        mine=self.get('works',self.worker)['data'][0];self.assertNotIn('client_rate',mine)
        today=self.get('today',self.worker)['data'];self.assertNotIn('finance',today);self.assertNotIn('debt',today)
        self.post('permissions',dict(user_id=self.worker_id,permissions={'payroll.own':False}))
        self.assertNotIn('salary',self.get('works',self.worker)['data'][0])
        self.request('/api/payroll/mine',self.worker,status=403)

    def test_technical_owner_explicit_context_required(self):
        self.request('/api/v3/meta',self.owner,status=403)
        result=self.request('/api/v3/meta',self.owner,extra_headers={'X-Portal-Company':'1'})
        self.assertTrue(result['ready'])
        self.request('/api/v3/work',self.owner,dict(request_id='owner-work',client_id=1,operation_id=1,quantity=1),status=400,extra_headers={'X-Portal-Company':'1'})
