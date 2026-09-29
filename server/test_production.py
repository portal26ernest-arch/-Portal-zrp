"""Production API tests. Only temporary fixtures, never a deployment database."""
import base64
import calendar
import hashlib
import io
import json
import sqlite3
import unittest
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from unittest.mock import patch
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

    def test_chat_stickers_absence_validation_idempotency_and_tenant_scope(self):
        for key in ('accepted','in_progress','done','help','important','thanks'):
            item=self.post('chat',dict(subtype='sticker',sticker_key=key))['data']
            self.assertEqual((item['message_type'],item['sticker_key']),('sticker',key))
        self.post('chat',dict(subtype='sticker',sticker_key='../x'),status=400)
        self.post('chat',dict(subtype='absence_notice',absence_date='2026-02-30',comment=''),status=400)
        self.post('chat',dict(subtype='absence_notice',absence_date='2026-09-29',comment='x'*301),status=400)
        notice=self.post('chat',dict(subtype='absence_notice',absence_date='2026-09-29',comment='Причина',request_id='absence-once'))['data']
        again=self.post('chat',dict(subtype='absence_notice',absence_date='2026-09-29',comment='Причина',request_id='absence-once'))['data']
        self.assertEqual(again['id'],notice['id'])
        rows=self.get('chat')['data']
        self.assertEqual(rows[-1]['absence_date'],'2026-09-29')
        self.assertEqual(next(row for row in rows if row.get('sticker_key')=='accepted')['message_type'],'sticker')
        self.get('chat',self.other_admin)
        self.assertEqual(self.get('chat',self.other_admin)['data'],[])
        self.post('chat',dict(subtype='absence_notice',absence_date='2026-09-29'),self.other_admin)

    def test_chat_write_capability_required_for_absence(self):
        self.post('permissions',dict(user_id=self.worker_id,permissions={'chat.read':True,'chat.write':False}))
        self.post('chat',dict(subtype='absence_notice',absence_date='2026-09-29'),self.worker,status=403)

    def test_marketplace_news_read_is_company_scoped_and_has_no_employee_write(self):
        with portal.db() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS marketplace_news(id INTEGER PRIMARY KEY AUTOINCREMENT,company_id INTEGER,source TEXT,title TEXT,body TEXT,url TEXT,published_at TEXT,fetched_at TEXT,is_regulation INTEGER,external_key TEXT,UNIQUE(company_id,external_key))''')
            conn.execute("INSERT INTO marketplace_news(company_id,source,title,body,url,published_at,fetched_at,is_regulation,external_key) VALUES(1,'ozon','A','Summary','https://seller.ozon.ru/a','2026-09-29','now',0,'a')")
            conn.execute("INSERT INTO marketplace_news(company_id,source,title,body,url,published_at,fetched_at,is_regulation,external_key) VALUES(2,'ozon','B','Summary','https://seller.ozon.ru/b','2026-09-29','now',0,'b')")
        rows=self.get('marketplace-news?source=ozon&limit=10')['data']
        self.assertEqual([row['title'] for row in rows],['A'])
        self.post('marketplace-news',dict(source='ozon',title='employee write'),status=400)

    def test_secure_invite_lifecycle_hashes_token_is_idempotent_and_scoped(self):
        body={'action':'create','role':'packer','username':'invited-one','display_name':'Invited One','request_id':'invite-create-once'}
        created=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        token=created['token'];identity=created['invite']['id']
        self.assertTrue(token.startswith('1.'))
        replay=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        self.assertEqual(replay['invite']['id'],identity);self.assertIsNone(replay['token']);self.assertTrue(replay['replay'])
        with portal.tenants.company_scope(1),portal.db() as conn:
            digest=hashlib.sha256(token.encode()).hexdigest()
            stored=conn.execute('SELECT token_hash,status FROM portal_access_invites WHERE id=?',(identity,)).fetchone()
            self.assertEqual((stored['token_hash'],stored['status']),(digest,'pending'))
            audit=' '.join(row['payload'] for row in conn.execute("SELECT payload FROM portal_production WHERE kind='audit'"))
            self.assertNotIn(token,audit)
        worker=self.role_token('packer')
        self.request('/api/v3/invitations',worker,status=403)
        self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST',extra_headers={'X-Portal-Company':'2'},status=403)
        accepted=self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST')['data']
        self.assertEqual(accepted['status'],'pending_approval')
        repeated=self.request('/api/access-invites/accept',body={'token':token,'pin':'9999'},method='POST')['data']
        self.assertEqual(repeated['status'],'pending_approval')
        pending=self.request('/api/v3/invitations?status=accepted',self.admin)['data']['items']
        self.assertEqual([row['id'] for row in pending],[identity])
        self.request('/api/v3/invitations',self.admin,{'action':'approve','invite_id':identity},method='POST')
        self.request('/api/login',body={'company_id':1,'username':'invited-one','pin':'6789'})
        self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST',status=403)
        audit=self.request('/api/v3/audit?limit=10',self.admin)['data']['items']
        invite_events=[row for row in audit if row['action'].startswith('access_invite.')]
        self.assertGreaterEqual(len(invite_events),3)
        self.assertTrue(all('summary' in row and 'token' not in str(row).lower() for row in invite_events))
        self.request('/api/v3/audit',self.worker,status=403)
        self.request('/api/v3/audit?company_id=2',self.admin,status=403)
        with portal.tenants.company_scope(1),portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM app_users WHERE username=?',('invited-one',)).fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT status FROM portal_access_invites WHERE id=?',(identity,)).fetchone()[0],'approved')

    def test_invite_revoke_and_role_capability_denials(self):
        manager=self.role_token('manager')
        body={'action':'create','role':'packer','username':'manager-invite','display_name':'Candidate','request_id':'manager-invite'}
        self.request('/api/v3/invitations',manager,body,method='POST',status=403)
        director=self.role_token('director')
        body['username']='director-invite';body['request_id']='director-invite'
        self.request('/api/v3/invitations',director,body,method='POST')
        self.request('/api/v3/invitations',director,body,method='POST',extra_headers={'X-Portal-Company':'2'},status=403)
        body['username']='owner-invite';body['request_id']='owner-invite'
        self.request('/api/v3/invitations',self.owner,body,method='POST',status=403)
        self.request('/api/v3/invitations',self.owner,body,method='POST',extra_headers={'X-Portal-Company':'1'})
        body['request_id']='invite-revoke'
        created=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        self.request('/api/v3/invitations',self.admin,{'action':'revoke','invite_id':created['invite']['id']},method='POST')
        self.request('/api/access-invites/accept',body={'token':created['token'],'pin':'6789'},method='POST',status=403)

    def test_company_access_summary_is_capability_and_owner_scope_checked(self):
        self.assertTrue(self.get('company-access')['data']['unlimited'])
        self.assertEqual(self.get('company-access')['data']['active_users'],2)
        self.get('company-access',self.role_token('manager'),status=403)
        self.assertIsInstance(self.get('company-access',self.role_token('director'))['data']['active_users'],int)
        self.request('/api/v3/company-access',self.owner,status=403)
        self.request('/api/v3/company-access',self.owner,extra_headers={'X-Portal-Company':'1'})

    def test_invitation_expiry_and_suspended_company_fail_closed(self):
        body={'action':'create','role':'packer','username':'expiry-candidate','display_name':'Candidate','request_id':'expiry-invite'}
        created=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        class ExpiredClock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.now(tz)+timedelta(days=8)
        with patch('access_invites.datetime',ExpiredClock):
            expired=self.request('/api/access-invites/accept',body={'token':created['token'],'pin':'6789'},method='POST')['data']
        self.assertEqual(expired['status'],'expired')
        with portal.tenants.control(portal.DB_PATH) as registry:
            registry.execute("UPDATE companies SET service_status='suspended' WHERE id=1")
        try:
            self.request('/api/access-invites/accept',body={'token':created['token'],'pin':'6789'},method='POST',status=403)
            self.request('/api/v3/invitations',self.admin,status=401)
        finally:
            with portal.tenants.control(portal.DB_PATH) as registry:registry.execute("UPDATE companies SET service_status='active' WHERE id=1")

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
        history=self.get('tariff-history?operation_id=1')['data']
        self.assertEqual(len(history),3)
        self.assertEqual(history[0]['employee_rate'],9900)
        self.assertEqual(history[-1]['employee_rate'],200)
        self.get('tariff-history?operation_id=1&company_id=2',status=403)
        self.post('permissions',dict(user_id=self.worker_id,permissions={'rates.client':True}))
        manager_history=self.get('tariff-history?operation_id=1',self.worker)['data']
        self.assertNotIn('employee_rate',manager_history[0])
        self.assertIn('client_rate',manager_history[0])
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

    def test_company_overhead_is_not_charged_to_random_client(self):
        self.work()
        before=self.get('finance')['data'];base=before['clients'][0]['profit']
        self.post('expenses',dict(category_code='rent',amount=10,incurred_at=datetime.now().date().isoformat(),note='Склад'))
        data=self.get('finance')['data']
        self.assertEqual(data['clients'][0]['profit'],base)
        self.assertEqual(data['company_overhead'],1000)
        self.assertEqual(data['net_profit'],base-1000)
        self.assertEqual(self.get('expenses')['data'][0]['category_code'],'rent')
        self.post('expenses',dict(category_code='unknown',amount=1),status=400)
        self.post('expenses',dict(category_code='rent',amount=1),self.worker,status=403)
        self.post('expenses',dict(category_code='logistics',amount=1,client_id=1))
        after=self.get('finance')['data']
        self.assertEqual(after['clients'][0]['profit'],base-100)
        self.assertEqual(after['company_overhead'],1000)

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

    def test_payroll_period_close_blocks_closed_dates_and_creates_document_snapshot(self):
        current=self.work()
        today=datetime.utcnow().date()
        if today.day>15:start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
        else:
            previous=(today.replace(day=1)-timedelta(days=1));start=previous.replace(day=16).isoformat();end=previous.isoformat()
        with portal.db() as conn:
            r=Repository(conn,1);old=dict(current,id=str(uuid.uuid4()),completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
            r.insert('works',{k:v for k,v in old.items() if k not in {'id','company_id'}},old['id']);conn.commit()
        preview=self.get(f'payroll-periods?period_start={start}&period_end={end}')['data']
        self.assertEqual(preview['total_salary'],400)
        closed=self.post('payroll-periods',dict(period_start=start,period_end=end))['data']
        self.assertEqual(closed['status'],'closed');self.assertEqual(closed['snapshot']['total_salary'],400)
        self.post('payroll-periods',dict(period_start=start,period_end=end),status=400)
        current_start=today.replace(day=1 if today.day<=15 else 16).isoformat()
        current_end=today.replace(day=15 if today.day<=15 else calendar.monthrange(today.year,today.month)[1]).isoformat()
        self.post('payroll-periods',dict(period_start=current_start,period_end=current_end),status=400)
        with portal.db() as conn:
            r=Repository(conn,1);u=next(u for u in r.catalog('users') if u['id']==self.worker_id)
            fixed=Production(r,u,lambda:end+'T23:00:00.000000')
            self.assertTrue(fixed.payroll_is_closed(end))
        document=self.post('documents',dict(document_type='payroll',period_start=start,period_end=end))['data']
        self.assertEqual(document['status'],'ready');self.assertEqual(len(document['sha256']),64)
        self.assertTrue(document['filename'].endswith('.xlsx'));self.assertGreater(document['size_bytes'],1000)
        listed=self.get('documents')['data'][0];self.assertEqual(listed['period_id'],closed['id']);self.assertNotIn('file_b64',listed)
        self.assertNotIn('details',listed['snapshot'])
        filedata=self.get('document-file?id='+document['id'])['data'];payload=base64.b64decode(filedata['file_b64'])
        self.assertEqual(hashlib.sha256(payload).hexdigest(),document['sha256']);self.assertEqual(len(payload),document['size_bytes'])
        with zipfile.ZipFile(io.BytesIO(payload)) as book:
            names=set(book.namelist());self.assertIn('xl/workbook.xml',names);self.assertIn('xl/worksheets/sheet1.xml',names)
            for name in names:
                if name.endswith('.xml') or name.endswith('.rels'):ET.fromstring(book.read(name))

    def test_chat_general_private_retention_pin_and_company_isolation(self):
        message=self.post('chat',dict(text='Общее сообщение'),self.worker)['data']
        self.assertEqual(self.get('chat',self.worker)['data'][0]['text'],'Общее сообщение')
        self.assertEqual(self.get('chat',self.other_worker)['data'],[])
        dm=self.post('chat',dict(text='Личное',recipient_user_id=self.admin_id),self.worker)['data']
        mine=self.get(f'chat?recipient_user_id={self.admin_id}',self.worker)['data']
        admin=self.get(f'chat?recipient_user_id={self.worker_id}',self.admin)['data']
        self.assertEqual(mine[-1]['id'],dm['id']);self.assertEqual(admin[-1]['id'],dm['id'])
        manager=self.role_token('manager')
        payload=(b'PORTAL-attachment-'*7000)
        uploaded=self.post('chat',dict(text='Файл',recipient_user_id=self.admin_id,attachment={
            'name':'proof.txt','mime_type':'text/plain','file_b64':base64.b64encode(payload).decode('ascii')
        }),self.worker)['data']
        attachment=uploaded['attachment']
        downloaded=self.get('chat-file?id='+attachment['id'],self.worker)['data']
        self.assertEqual(base64.b64decode(downloaded['file_b64']),payload)
        self.assertEqual(downloaded['sha256'],hashlib.sha256(payload).hexdigest())
        self.get('chat-file?id='+attachment['id'],manager,status=403)
        self.post('chat',dict(mode='pin',message_id=dm['id'],pinned=True),manager,status=403)
        with portal.db() as conn:
            r=Repository(conn,1)
            expired=r.insert('chat_messages',dict(room='general',sender_user_id=self.worker_id,sender_name='Old',
                                                   text='Удалить',created_at='2020-01-01T00:00:00.000000'))
            kept=r.insert('chat_messages',dict(room='general',sender_user_id=self.worker_id,sender_name='Pinned',
                                                text='Сохранить',created_at='2020-01-01T00:00:00.000000'))
            r.insert('chat_pins',dict(message_id=kept['id'],room='general',pinned=True,actor_id=self.admin_id))
            conn.commit()
        visible=self.get('chat')['data'];ids={x['id'] for x in visible}
        self.assertNotIn(expired['id'],ids);self.assertIn(kept['id'],ids)
        self.assertTrue(next(x for x in visible if x['id']==kept['id'])['pinned'])
        with portal.db() as conn:
            r=Repository(conn,1)
            self.assertIsNone(r.get('chat_messages',expired['id'],False))
            self.assertIsNotNone(r.get('chat_messages',kept['id'],False))
            with self.assertRaises(ValueError):r.delete('works',message['id'])
        self.post('chat',dict(mode='pin',message_id=message['id'],pinned=True),self.worker,status=403)

    def test_large_request_body_exception_is_chat_only(self):
        result=self.request('/api/v3/batches',self.admin,{'request_id':'oversize','client_id':1,'product':'X','quantity':1,'comment':'x'*70000},status=400)
        self.assertIn('64',result['error'])
        payload=b'a'*70000
        sent=self.post('chat',dict(text='Большой файл',attachment={'name':'a.txt','mime_type':'text/plain','file_b64':base64.b64encode(payload).decode('ascii')}),self.worker)['data']
        self.assertEqual(sent['attachment']['size_bytes'],len(payload))

    def test_chat_attachment_security_hash_and_retention(self):
        raw=b'PORTAL attachment'
        attachment=dict(name='note.txt',mime_type='text/plain',file_b64=base64.b64encode(raw).decode())
        sent=self.post('chat',dict(text='Файл',attachment=attachment),self.worker)['data']
        self.assertIn('attachment',sent);meta=sent['attachment'];self.assertNotIn('file_b64',meta)
        rows=self.get('chat',self.worker)['data'];listed=next(x for x in rows if x['id']==sent['id'])
        self.assertEqual(listed['attachment']['sha256'],hashlib.sha256(raw).hexdigest())
        filedata=self.get('chat-file?id='+meta['id'],self.worker)['data']
        self.assertEqual(base64.b64decode(filedata['file_b64']),raw)
        self.assertEqual(filedata['sha256'],hashlib.sha256(raw).hexdigest())
        self.get('chat-file?id='+meta['id'],self.other_worker,status=400)
        self.post('chat',dict(text='Bad',attachment=dict(name='x.exe',mime_type='application/octet-stream',file_b64='WA==')),self.worker,status=400)
        too_big=base64.b64encode(b'x'*(2*1024*1024+1)).decode()
        self.post('chat',dict(attachment=dict(name='big.txt',mime_type='text/plain',file_b64=too_big)),self.worker,status=400)
        with portal.db() as conn:
            r=Repository(conn,1)
            old=r.insert('chat_messages',dict(room='general',sender_user_id=self.worker_id,sender_name='Old',text='',created_at='2020-01-01T00:00:00.000000'))
            old_file=r.insert('chat_attachments',dict(message_id=old['id'],room='general',original_name='old.txt',filename='PORTAL_chat_old.txt',mime_type='text/plain',size_bytes=1,sha256=hashlib.sha256(b'x').hexdigest(),file_b64='eA==',created_at='2020-01-01T00:00:00.000000'))
            conn.commit()
        self.get('chat',self.worker)
        with portal.db() as conn:
            r=Repository(conn,1)
            self.assertIsNone(r.get('chat_messages',old['id'],False))
            self.assertIsNone(r.get('chat_attachments',old_file['id'],False))

    def test_technical_owner_explicit_context_required(self):
        self.request('/api/v3/meta',self.owner,status=403)
        result=self.request('/api/v3/meta',self.owner,extra_headers={'X-Portal-Company':'1'})
        self.assertTrue(result['ready'])
        self.request('/api/v3/work',self.owner,dict(request_id='owner-work',client_id=1,operation_id=1,quantity=1),status=400,extra_headers={'X-Portal-Company':'1'})
