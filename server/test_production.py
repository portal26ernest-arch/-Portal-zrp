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
from production_repository import Repository, utcnow
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

    def test_product_catalog_uses_stable_client_ids_and_preserves_batch_snapshots(self):
        created=self.post('products',dict(action='create',client_id=1,name='Catalog box'))['data']
        self.assertEqual((created['client_id'],created['name'],created['active']),(1,'Catalog box',True))
        batch=self.post('batches',dict(client_id=1,product_id=created['id'],quantity=4))['data']
        self.assertEqual((batch['product_id'],batch['product']),(created['id'],'Catalog box'))
        updated=self.post('products',dict(action='update',product_id=created['id'],name='Renamed box'))['data']
        self.assertEqual(updated['id'],created['id'])
        self.assertEqual(self.get('catalog')['data']['products'][0]['name'],'Renamed box')
        self.assertEqual(next(row for row in self.get('batches')['data'] if row['id']==batch['id'])['product'],'Catalog box')
        manager=self.role_token('manager')
        self.request('/api/v3/products',manager,body={'request_id':'manager-product-create','action':'create','client_id':1,'name':'Forbidden'},method='POST',status=403)
        self.request('/api/v3/products',self.other_admin,body={'request_id':'foreign-product','action':'update','product_id':created['id'],'name':'Forged'},method='POST',status=400)
        archived=self.post('products',dict(action='archive',product_id=created['id']))['data']
        self.assertFalse(archived['active'])
        self.assertEqual(self.get('catalog')['data']['products'],[])
        self.post('batches',dict(client_id=1,product_id=created['id'],quantity=1),status=400)

    def test_client_requisites_are_company_scoped_editable_and_audited_without_values(self):
        with portal.db() as conn:
            conn.execute('DROP TABLE portal_client_requisites')
            conn.execute('''CREATE TABLE portal_client_requisites(
                company_id INTEGER NOT NULL,client_id INTEGER NOT NULL,legal_name TEXT,inn TEXT,kpp TEXT,ogrn TEXT,
                legal_address TEXT,settlement_account TEXT,bank_name TEXT,bik TEXT,correspondent_account TEXT,
                phone TEXT,email TEXT,contact_person TEXT,tax_info TEXT,updated_at TEXT NOT NULL,updated_by INTEGER,
                PRIMARY KEY(company_id,client_id))''')
        values={'legal_name':'ООО Тест','inn':'TEST-INN-001','bank_name':'Тестовый банк',
                'settlement_account':'TEST-ACCOUNT-SECRET','email':'client@example.invalid'}
        body=dict(client_id=1,**values,request_id='client-requisites-create-once')
        first=self.request('/api/v3/client-requisites',self.admin,body,method='POST')['data']
        retry=self.request('/api/v3/client-requisites',self.admin,body,method='POST')['data']
        self.assertEqual(first,retry)
        self.assertEqual(self.get('client-requisites?client_id=1')['data']['inn'],values['inn'])
        self.assertEqual(self.get('client-requisites?client_id=1',self.other_admin)['data'],{})
        self.request('/api/v3/client-requisites?client_id=1',self.admin,status=403,
                     extra_headers={'X-Portal-Company':str(self.other)})
        self.request('/api/v3/client-requisites',self.admin,dict(client_id=1,company_id=self.other,inn='x'),method='POST',status=403)
        self.request('/api/v3/client-requisites',self.admin,dict(client_id=1,unknown='x'),method='POST',status=400)
        self.request('/api/v3/client-requisites',self.admin,dict(client_id=1,inn=123),method='POST',status=400)
        manager=self.role_token('manager')
        self.request('/api/v3/client-requisites',manager,dict(client_id=1,inn='forbidden'),method='POST',status=403)
        with portal.tenants.company_scope(1),portal.db() as conn:
            row=conn.execute('SELECT company_id,client_id,updated_by FROM portal_client_requisites').fetchone()
            self.assertEqual(tuple(row),(1,1,self.admin_id))
            audits=[json.loads(row['payload']) for row in conn.execute(
                "SELECT payload FROM portal_production WHERE company_id=1 AND kind='audit'")]
        event=next(item for item in audits if item.get('event')=='client.requisites.updated')
        self.assertEqual(event['entity_id'],'1')
        serialized=json.dumps(event,ensure_ascii=False)
        for secretish in values.values():self.assertNotIn(secretish,serialized)
        self.assertEqual(self.get('audit?action=client.requisites.updated')['data']['total'],1)

    def test_client_rename_keeps_stable_id_and_work_snapshot_and_appends_name_history(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            original=portal.get_client(conn,1)['name']
            Repository(conn,1).insert('works',dict(client_id=1,client_name=original,operation_name='Packing',
                quantity=1,salary=100,revenue=200,completed_at=utcnow()),'rename-history-work')
            conn.commit()
        response=self.request('/api/admin/clients/1',self.admin,{'name':'Canonical client rename'},method='POST')
        renamed_id=response['id']
        self.assertEqual(renamed_id,1)
        with portal.tenants.company_scope(1),portal.db() as conn:
            current=portal.get_client(conn,1)
            work=Repository(conn,1).get('works','rename-history-work')
            history=Repository(conn,1).list('client_name_history')
            audit=Repository(conn,1).list('audit')
        self.assertEqual(current['name'],'Canonical client rename')
        self.assertEqual(work['client_name'],original)
        self.assertEqual([(row['old_name'],row['new_name']) for row in history],[(original,'Canonical client rename')])
        self.assertIn('client.renamed',[row['event'] for row in audit])
        self.assertEqual(self.get('client-name-history?client_id=1')['data'],history)
        self.assertEqual(self.get('client-name-history')['data'],history)
        self.assertEqual(self.get('client-name-history',self.other_admin)['data'],[])
        self.assertEqual(self.get('client-name-history?client_id=1',self.other_admin)['data'],[])

    def test_today_dashboard_has_company_date_volume_finance_and_open_invoice_counts(self):
        work=self.work()
        self.post('invoices',dict(work_ids=[work['id']],due_at='2020-01-01'))
        today=datetime.utcnow().date()
        closed_payroll=None
        if today.day>15:
            start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
            with portal.tenants.company_scope(1),portal.db() as conn:
                historical=dict(Repository(conn,1).get('works',work['id']),
                                completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
                for key in ('id','company_id'):historical.pop(key,None)
                Repository(conn,1).insert('works',historical)
                conn.commit()
            period=self.post('payroll-periods',dict(period_start=start,period_end=end))['data']
            legacy_employee=period['snapshot']['employees'][0]['employee_id']
            with portal.tenants.company_scope(1),portal.db() as conn:
                employee=Repository(conn,1).payroll_employee(legacy_employee,legacy=True)['employee_id']
            self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=employee,
                entry_type='payout',amount='1.00',reason='Dashboard test',request_id='dashboard-paid-once'))
            closed_payroll=(400,100,300)
        with portal.tenants.company_scope(1),portal.db() as conn:
            dashboard_repo=Repository(conn,1)
            dashboard_user=next(user for user in dashboard_repo.catalog('users') if user['id']==self.admin_id)
            Production(dashboard_repo,dashboard_user).today()
        data=self.get('today')['data']
        self.assertEqual(data['today_quantity'],2)
        self.assertEqual(data['month_quantity'],4)
        self.assertEqual(data['today_finance'],dict(revenue=1000,salary=400))
        self.assertEqual((data['month_finance']['revenue'],data['month_finance']['salary']),(2000,800))
        self.assertEqual(data['today_productivity']['units'],2)
        self.assertIsNone(data['today_productivity']['units_per_hour'])
        self.assertEqual((data['open_invoice_count'],data['overdue_invoice_count'],data['overdue_debt']),(1,1,1000))
        self.assertIsNone(data['expected_profit'])
        if closed_payroll is None:self.assertIsNone(data['closed_month_payroll'])
        else:self.assertEqual((data['closed_month_payroll']['accrued'],data['closed_month_payroll']['paid'],data['closed_month_payroll']['balance']),closed_payroll)

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

    def test_company_audit_entity_date_filters_pagination_and_safe_summary(self):
        created=[]
        for n in ('audit-first','audit-second'):
            created.append(self.post('invitations',dict(action='create',role='packer',username=n,
                display_name=n,request_id=n))['data'])
        first_id=created[0]['invite']['id']
        filtered=self.get('audit?action=access_invite.created&entity_id='+first_id+
            '&from=2026-01-01&to=2099-12-31&limit=10')['data']
        self.assertEqual(filtered['total'],1)
        row=filtered['items'][0]
        self.assertEqual((row['action'],row['entity_id']),('access_invite.created',first_id))
        self.assertEqual(row['actor_id'],1)
        self.assertEqual(row['summary'],'Создано приглашение')
        self.assertNotIn('token',json.dumps(row).lower());self.assertNotIn('pin',json.dumps(row).lower())
        first_page=self.get('audit?action=access_invite.created&from=2026-01-01&to=2099-12-31&page=1&limit=1')['data']
        second_page=self.get('audit?action=access_invite.created&from=2026-01-01&to=2099-12-31&page=2&limit=1')['data']
        self.assertGreaterEqual(first_page['total'],2)
        self.assertEqual((len(first_page['items']),len(second_page['items'])),(1,1))
        self.assertNotEqual(first_page['items'][0]['id'],second_page['items'][0]['id'])
        self.assertGreaterEqual(first_page['items'][0]['at'],second_page['items'][0]['at'])
        self.get('audit?entity_id='+first_id+'&company_id=2',status=403)
        self.get('audit',self.worker,status=403)

    def test_company_settings_and_capability_changes_are_audited_without_values(self):
        self.post('settings',dict(monday_time='11:30',utc_offset_minutes=240))
        self.post('permissions',dict(user_id=self.worker_id,permissions={'work.write':False}))
        settings=self.get('audit?action=company.settings.updated')['data']['items']
        capabilities=self.get('audit?action=user.permissions.updated')['data']['items']
        self.assertEqual((settings[0]['entity_id'],settings[0]['summary']),
                         ('control','Изменены настройки компании'))
        self.assertEqual((capabilities[0]['entity_id'],capabilities[0]['summary']),
                         (str(self.worker_id),'Изменены права сотрудника'))
        with portal.tenants.company_scope(1),portal.db() as conn:
            rows=[json.loads(row['payload']) for row in conn.execute(
                "SELECT payload FROM portal_production WHERE company_id=1 AND kind='audit'")]
        events={row['event']:row for row in rows if row.get('event') in
                ('company.settings.updated','user.permissions.updated')}
        self.assertEqual(events['company.settings.updated']['fields'],['monday_time','utc_offset_minutes'])
        self.assertEqual(events['user.permissions.updated']['fields'],['work.write'])
        serialized=json.dumps(events,ensure_ascii=False)
        for value in ('11:30','240','true'):
            self.assertNotIn(value,serialized)

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

    def test_internal_shipment_completion_is_idempotent_and_audited(self):
        batch=self.batch()
        task=self.task(batch)
        self.work(task_id=task['id'])
        self.post('work',dict(task_id=task['id'],quantity=8),self.worker)
        body=dict(batch_id=batch['id'],direction='FBS',request_id='shipment-complete-once')
        first=self.post('shipments',body)['data']
        replay=self.post('shipments',body)['data']
        self.assertEqual(first['id'],replay['id'])
        self.assertEqual((first['direction'],first['quantity']),('FBS',10))
        rows=[row for row in self.get('shipments')['data'] if row['batch_id']==batch['id']]
        self.assertEqual(len(rows),1)
        with portal.tenants.company_scope(1),portal.db() as conn:
            repository=Repository(conn,1)
            events=[row for row in repository.list('audit') if row.get('entity_id')==first['id']]
            self.assertEqual(len(events),1)
        self.post('shipments',dict(batch_id=batch['id'],direction='FBO',request_id='shipment-complete-once'),status=400)

    def test_without_task_and_later_link_preserve_money(self):
        w=self.work();self.assertTrue(w['without_task']);self.assertIsNone(w['batch_id'])
        before=self.get('works')['data'][0];b=self.batch()
        self.post('links',dict(work_id=w['id'],batch_id=b['id']))
        after=self.get('works')['data'][0]
        self.assertEqual((before['salary'],before['revenue']),(after['salary'],after['revenue']))
        self.assertEqual(after['batch_id'],b['id'])
        self.post('links',dict(work_id=w['id'],batch_id=b['id']),status=400)

    def test_internal_return_workflow_is_idempotent_scoped_and_does_not_post_work(self):
        batch=self.post('batches',dict(client_id=1,product='Коробка',quantity=4))['data']
        task=self.post('tasks',dict(batch_id=batch['id'],operation_id=1,quantity=4,assignees=[self.worker_id]))['data']
        work=self.post('work',dict(task_id=task['id'],quantity=4),self.worker)['data']
        before_work=len(self.get('works')['data'])
        self.post('shipments',dict(batch_id=batch['id'],direction='FBS'))
        body=dict(batch_id=batch['id'],quantity=1,condition='damaged',comment='Упаковка повреждена',request_id='return-part-1')
        first=self.post('returns',body)['data']
        replay=self.post('returns',body)['data']
        self.assertEqual(first['id'],replay['id'])
        self.assertEqual((first['returned_quantity'],first['returnable_quantity']),(1,3))
        current=next(row for row in self.get('batches')['data'] if row['id']==batch['id'])
        self.assertEqual((current['stage'],current['returned_quantity'],current['returnable_quantity']),('partially_returned',1,3))
        self.post('returns',dict(batch_id=batch['id'],quantity=4,condition='unknown'),status=400)
        final=self.post('returns',dict(batch_id=batch['id'],quantity=3,condition='resalable'))['data']
        self.assertEqual((final['returned_quantity'],final['returnable_quantity']),(4,0))
        current=next(row for row in self.get('batches')['data'] if row['id']==batch['id'])
        self.assertEqual(current['stage'],'returned')
        self.post('returns',dict(batch_id=batch['id'],quantity=1),status=400)
        self.assertEqual(len(self.get('works')['data']),before_work)
        self.assertEqual(len([row for row in self.get('shipments')['data'] if row.get('type')=='return']),2)
        self.post('returns',dict(batch_id=batch['id'],quantity=1),self.worker,status=403)

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

    def test_tariff_effective_boundary_preserves_prior_work_and_rejects_duplicate_interval(self):
        before=self.work()
        future=(datetime.fromisoformat(utcnow())+timedelta(days=1)).replace(microsecond=0).isoformat()
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=3,effective_from=future))
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=4,effective_from=future),status=400)
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            worker=next(user for user in repo.catalog('users') if user['id']==self.worker_id)
            after_at=(datetime.fromisoformat(future)+timedelta(seconds=1)).isoformat()
            after=Production(repo,worker,clock=lambda:after_at).work(dict(client_id=1,operation_id=1,quantity=2))
            conn.commit()
        old=self.get('works')['data']
        self.assertEqual((before['salary'],before['employee_rate']),(400,200))
        self.assertEqual(next(row for row in old if row['id']==before['id'])['salary'],400)
        self.assertEqual((after['salary'],after['employee_rate']),(600,300))
        self.assertEqual(len(self.get('tariff-history?operation_id=1')['data']),2)

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

    def test_batch_economy_marks_missing_plan_unavailable_instead_of_zero(self):
        batch=self.batch()
        economy=self.get('economy?batch_id='+batch['id'])['data']
        for key in ('salary','revenue','materials','other','profit','volume'):
            self.assertIsNone(economy['plan'][key],key)
            self.assertIsNone(economy['deviation'][key],key)
        self.assertEqual(economy['fact']['volume'],0)
        self.assertEqual(economy['fact']['profit'],0)

    def test_persisted_reminder_appears_only_in_authorized_company_attention(self):
        from production_repository import Repository
        with portal.tenants.company_scope(1),portal.db() as conn:
            Repository(conn,1).insert_once('notifications',dict(event='reminder',reminder_kind='invoice_overdue',
                entity_id='invoice-1',title='Просрочена оплата по счёту',idempotency_key='reminder:invoice_overdue:invoice-1:2026-09-30',
                occurred_at='2026-09-30T12:00:00+00:00'),'reminder:invoice_overdue:invoice-1:2026-09-30')
            conn.commit()
        today=self.get('today')['data']
        self.assertTrue(any(item.get('type')=='reminder' and item.get('entity_id')=='invoice-1' for item in today['attention']))
        worker_today=self.get('today',self.worker)['data']
        self.assertFalse(any(item.get('type')=='reminder' for item in worker_today['attention']))

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

    def test_receivables_aging_boundaries_partial_payment_and_cents_reconcile(self):
        today=(datetime.fromisoformat(utcnow())+timedelta(minutes=180)).date()
        offsets=(0,1,7,8,30,31,60,61);created=[]
        for index,days in enumerate(offsets):
            work=self.work();due=(today-timedelta(days=days)).isoformat()
            invoice=self.post('invoices',dict(work_ids=[work['id']],due_at=due))['data'];created.append(invoice)
            if index==2:self.post('payments',dict(invoice_id=invoice['id'],amount='4.00'))
        report=self.get('receivables')['data']
        self.assertEqual(report['money_unit'],'kopeck')
        self.assertEqual((report['outstanding'],report['overdue']),(7600,6600))
        self.assertEqual({key:value['count'] for key,value in report['buckets'].items() if key!='undated'},
                         {'current':1,'days_1_7':2,'days_8_30':2,'days_31_60':2,'days_61_plus':1})
        self.assertEqual(report['buckets']['days_1_7']['amount'],1600)
        self.assertEqual(sum(bucket['amount'] for bucket in report['buckets'].values()),report['outstanding'])
        self.assertEqual(report['clients'][0]['outstanding'],report['outstanding'])
        page=self.get('receivables?page=2&limit=3')['data']
        self.assertEqual((page['page'],page['limit'],page['total'],len(page['items'])),(2,3,8,3))
        self.assertEqual(page['outstanding'],report['outstanding'])
        self.get('receivables?client_id=9999',status=403)
        self.get('receivables',self.worker,status=403)

    def test_receivable_timezone_offset_uses_company_local_due_date(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            repo.insert('settings',dict(utc_offset_minutes=180),'control')
            repo.insert('invoices',dict(client_id=1,client_name='Client',amount=500,due_at='2026-09-30T23:30:00+03:00',
                work_ids=[],lines=[],state='finalized'),'offset-due-invoice')
            conn.commit()
            user=next(item for item in repo.catalog('users') if item['id']==self.admin_id)
            service=Production(repo,user,clock=lambda:'2026-09-30T21:30:00')
            result=service.receivables({'page':['1'],'limit':['50']})
            dashboard=service.today()
        self.assertEqual(result['as_of'],'2026-10-01')
        self.assertEqual((result['items'][0]['overdue_days'],result['items'][0]['bucket']),(1,'days_1_7'))
        self.assertEqual((dashboard['date'],dashboard['overdue_invoice_count'],dashboard['overdue_debt']),("2026-10-01",1,500))

    def test_finance_monthly_trend_uses_company_local_month(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            repo.insert('settings',dict(utc_offset_minutes=180),'control')
            repo.insert('works',dict(client_id=1,client_name='Client',operation_id=1,operation_name='Packing',
                quantity=1,salary=100,revenue=200,completed_at='2026-09-30T22:30:00+00:00'),'month-boundary-work')
            conn.commit()
            user=next(item for item in repo.catalog('users') if item['id']==self.admin_id)
            result=Production(repo,user,clock=lambda:'2026-10-01T00:00:00').finance()
        self.assertNotIn('2026-09',result['months'])
        self.assertEqual(result['months']['2026-10']['revenue'],200)
        self.assertEqual(result['months']['2026-10']['salary'],100)

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

    def test_analytics_period_comparison_uses_company_dates_and_valid_timing_only(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1);worker=next(user for user in repo.catalog('users') if user['id']==self.worker_id)
            Production(repo,worker,lambda:'2026-10-05T12:00:00.000000').work(
                dict(client_id=1,operation_id=1,quantity=1))
            Production(repo,worker,lambda:'2026-10-12T12:00:00.000000').work(
                dict(client_id=1,operation_id=1,quantity=2,started_at='2026-10-12T11:00:00.000000'))
            conn.commit()
        data=self.get('analytics?from=2026-10-10&to=2026-10-16',self.worker)['data']
        comparison=data['comparison']
        self.assertEqual((comparison['previous_start'],comparison['previous_end']),('2026-10-03','2026-10-09'))
        self.assertEqual((comparison['current']['units'],comparison['previous']['units'],comparison['units_delta']),(2,1,1))
        self.assertEqual(comparison['current']['units_per_hour'],2)
        self.assertIsNone(comparison['previous']['units_per_hour'])
        self.assertIsNone(comparison['units_per_hour_delta'])
        self.assertEqual(sum(group['quantity'] for group in data['groups']),2)
        self.get('analytics?from=2026-10-10',self.worker,status=400)
        self.get('analytics?from=2026-10-17&to=2026-10-10',self.worker,status=400)

    def test_multiple_operations_do_not_double_count_finished_units(self):
        b=self.batch();t=self.task(b);self.post('work',dict(task_id=t['id'],quantity=10),self.worker)
        op=portal.save_operation(dict(name='Проверка',employee_rate=1,client_rate=2),1)
        self.post('tasks',dict(batch_id=b['id'],operation_id=op,quantity=10,assignees=[self.worker_id]))
        progress=self.get('batches')['data'][0];self.assertEqual(progress['done'],0);self.assertFalse(progress['ready'])

    def test_control_schedule_and_uninvoiced_separate_from_debt(self):
        self.work();director=self.role_token('director');manager=self.role_token('manager')
        self.assertEqual(self.get('settings',director)['data']['monday_time'],'10:00')
        self.post('settings',dict(monday_time='11:00',wednesday_time='12:00',utc_offset_minutes=0),director)
        self.get('settings',manager,status=403)
        self.post('settings',dict(monday_time='09:00'),manager,status=403)
        self.request('/api/v3/settings',self.admin,extra_headers={'X-Portal-Company':'2'},status=403)
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
