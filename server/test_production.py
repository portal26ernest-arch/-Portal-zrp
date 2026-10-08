"""Production API tests. Only temporary fixtures, never a deployment database."""
import base64
import calendar
import hashlib
import io
import json
import os
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
import production_permissions as rights

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

    def test_repository_list_by_sqlite_parity(self):
        with portal.tenants.company_scope(1), portal.db() as conn:
            repo=Repository(conn,1)
            rows=repo.list_by('tariffs',operation_id=1)
            self.assertTrue(rows)
            self.assertTrue(all(row['operation_id']==1 for row in rows))
            self.assertEqual(repo.list_by('tariffs',operation_id=999999),[])

    def test_current_role_matrix_defaults_are_exact_and_salary_safe(self):
        self.assertEqual(rights.defaults('director'),rights.CODES)
        self.assertEqual(rights.defaults('admin'),rights.CODES)
        manager=rights.defaults('manager')
        required={'work.write','tasks.read','tasks.manage','organizer.read','organizer.assign',
                  'organizer.request.create','batches.receive','work.link','payroll.own',
                  'chat.read','chat.write','chat.moderate','clients.read','rates.client',
                  'materials.read','materials.use','invoices.read','invoices.create','invoices.export',
                  'finance.read','expenses.read','analytics.read','documents.read'}
        forbidden={'payroll.all','payroll.close','payroll.settlement.read','payroll.settlement.payout',
                   'payroll.settlement.correct','users.manage','company.settings','imports.manage','rates.employee'}
        self.assertTrue(required <= manager)
        self.assertTrue(forbidden.isdisjoint(manager))
        worker_defaults={'tasks.read','work.write','payroll.own','materials.read','materials.use'}
        self.assertEqual(rights.defaults('packer'),worker_defaults)
        self.assertEqual(rights.defaults('loader'),worker_defaults)
        self.assertEqual(rights.defaults('driver'),worker_defaults)
        self.assertEqual(rights.defaults('shift'),set())
        self.assertEqual(rights.defaults('accountant'),set())

    def test_code_interpreter_is_server_only_role_scoped_and_audited(self):
        manager=self.role_token('manager');director=self.role_token('director')
        disabled={'PORTAL_CODE_INTERPRETER_ENABLED':'false','OPENAI_API_KEY':''}
        with patch.dict(portal.os.environ,disabled,clear=False):
            status=self.get('code-interpreter',self.admin)['data']
            self.assertFalse(status['enabled']);self.assertFalse(status['configured'])
            self.get('code-interpreter',self.worker,status=403)
            self.get('code-interpreter',manager,status=403)
            self.post('code-interpreter',dict(prompt='2+2'),self.admin,status=503)

        enabled={'PORTAL_CODE_INTERPRETER_ENABLED':'true','PORTAL_CODE_INTERPRETER_MODEL':'gpt-5.4-mini',
                 'PORTAL_CODE_INTERPRETER_MEMORY':'1g','OPENAI_API_KEY':'test-only-secret'}
        fake={'text':'4','response_id':'resp_route','model':'gpt-5.4-mini','container_id':'cntr_route'}
        with patch.dict(portal.os.environ,enabled,clear=False),patch('openai_code_interpreter.run',return_value=fake) as run:
            result=self.post('code-interpreter',dict(prompt='Посчитай 2+2'),director)['data']
            self.assertEqual(result['text'],'4')
            run.assert_called_once()
            self.post('code-interpreter',dict(prompt='x',unexpected=True),director,status=400)
        with portal.tenants.company_scope(1),portal.db() as conn:
            audits=[json.loads(row['payload']) for row in conn.execute(
                "SELECT payload FROM portal_production WHERE company_id=1 AND kind='audit'")]
        event=next(item for item in audits if item.get('event')=='ai.code_interpreter.used')
        serialized=json.dumps(event,ensure_ascii=False)
        self.assertEqual(event['entity_id'],'resp_route')
        self.assertNotIn('Посчитай 2+2',serialized)
        self.assertNotIn('test-only-secret',serialized)

    def test_direct_employee_account_creation_for_admin_and_director(self):
        director=self.role_token('director')
        manager=self.role_token('manager')
        director_created=self.request('/api/users',director,dict(username='direct-worker',display_name='Direct Worker',role='packer',pin='Pass-1234',create_employee=True,active=1))
        admin_created=self.request('/api/users',self.admin,dict(username='admin-worker',display_name='Admin Worker',role='packer',pin='Pass-5678',create_employee=True,active=1))
        self.assertTrue(director_created['id']);self.assertTrue(admin_created['id'])
        directory=self.request('/api/users',director)
        direct=next(row for row in directory['users'] if row['username']=='direct-worker')
        admin=next(row for row in directory['users'] if row['username']=='admin-worker')
        self.assertIsNotNone(direct['employee_id']);self.assertIsNotNone(admin['employee_id'])
        self.request('/api/users',manager,dict(username='forbidden-direct',display_name='Forbidden',role='packer',pin='1234',create_employee=True,active=1),status=403)

    def test_current_work_api_rejects_legacy_employee_field_without_writing(self):
        before=len(self.get('works',self.worker)['data'])
        self.post('work',dict(client_id=1,operation_id=1,quantity=2,telegram_id=101),self.worker,status=400)
        self.assertEqual(len(self.get('works',self.worker)['data']),before)

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

    def test_authenticated_runtime_identity_and_catalog_are_canonical_and_company_scoped(self):
        user=self.request('/api/me',self.worker)['user']
        self.assertIn('employee_id',user)
        self.assertNotIn('telegram_id',user)
        with portal.tenants.company_scope(1),portal.db() as conn:
            legacy=conn.execute('SELECT telegram_id FROM app_users WHERE id=?',(self.worker_id,)).fetchone()[0]
            self.assertNotEqual(user['employee_id'],legacy)
            repository=Repository(conn,1)
            self.assertEqual(repository.legacy_identity_for_employee(user['employee_id']),legacy)
            self.assertEqual(repository.employee_identity_for_legacy(legacy),user['employee_id'])
            catalog_user=next(item for item in repository.catalog('users') if item['id']==self.worker_id)
            self.assertEqual(catalog_user['employee_id'],user['employee_id'])
            self.assertNotIn('telegram_id',catalog_user)
        api_users=self.request('/api/users',self.admin)
        self.assertTrue(all('telegram_id' not in item for item in api_users['users']))
        self.assertTrue(all('employee_id' in item for item in api_users['employees']))
        self.request('/api/users',self.admin,{'username':'legacy-api','display_name':'Legacy API',
            'pin':'4321','role':'packer','telegram_id':101},status=400)
        foreign_identity=None
        with portal.tenants.company_scope(self.other),portal.db() as conn:
            conn.executemany('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,?,?,?)',
                             [(self.other,800+i,'Foreign '+str(i),'foreign-'+str(i)) for i in range(6)])
            repository=Repository(conn,self.other);repository.sync_payroll_employees();conn.commit()
            foreign_identity=max(item['employee_id'] for item in repository.employee_catalog())
        with portal.tenants.company_scope(1),portal.db() as conn:
            repository=Repository(conn,1)
            with self.assertRaises(ValueError):repository.legacy_identity_for_employee(foreign_identity)
            self.assertNotIn('telegram_id',repository.employee_catalog()[0])

    def test_manager_assignment_catalog_uses_canonical_employee_id(self):
        manager=self.role_token('manager')
        manager_id=self.request('/api/me',manager)['user']['employee_id']
        with portal.tenants.company_scope(1),portal.db() as conn:
            conn.execute('INSERT INTO manager_client_assignments(telegram_id,client_id,active) VALUES(101,1,1)')
            rows=Repository(conn,1).catalog('assignments')
        assignment=next(item for item in rows if item['client_id']==1 and item['active'])
        self.assertEqual(assignment['employee_id'],manager_id)
        self.assertNotIn('telegram_id',assignment)

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
            aliases=Repository(conn,1).list('client_aliases')
            audit=Repository(conn,1).list('audit')
        self.assertEqual(current['name'],'Canonical client rename')
        self.assertEqual(work['client_name'],original)
        self.assertEqual([(row['old_name'],row['new_name']) for row in history],[(original,'Canonical client rename')])
        rename_alias=next(row for row in aliases if row['client_id']==1 and row['alias']==original)
        self.assertEqual(rename_alias['source'],'rename')
        self.assertIn('client.renamed',[row['event'] for row in audit])
        self.assertEqual(self.get('client-name-history?client_id=1')['data'],history)
        self.assertEqual(self.get('client-name-history')['data'],history)
        self.assertEqual(self.get('client-aliases?client_id=1')['data'],[row for row in aliases if row['client_id']==1])
        self.assertEqual(self.get('client-name-history',self.other_admin)['data'],[])
        self.assertEqual(self.get('client-name-history?client_id=1',self.other_admin)['data'],[])
        self.assertEqual(self.get('client-aliases',self.other_admin)['data'],[])

    def test_known_client_alias_is_persisted_without_rewriting_canonical_name(self):
        from client_names import known_client_aliases
        expected={'Борискин':('Борисенко',),'Варданян':('Вартанян',),'Вдовина':('Вдовин',),
                  'Шульгина':('Шульгинова',),'Элегантика':('Эленгатика',),
                  'Карягин':('Корягин','Коорягин'),'Чотчаева':('Чотчаев',)}
        for canonical,aliases in expected.items():
            self.assertEqual(known_client_aliases(canonical),aliases)
        created=self.request('/api/admin/clients',self.admin,{'name':'Борискин'})
        client_id=created['id']
        aliases=self.get('client-aliases?client_id='+str(client_id))['data']
        self.assertEqual([(row['alias'],row['source']) for row in aliases],[('Борисенко','knowledge')])
        self.assertEqual(self.get('client-name-history?client_id='+str(client_id))['data'],[])
        with portal.tenants.company_scope(1),portal.db() as conn:
            self.assertEqual(portal.get_client(conn,client_id)['name'],'Борискин')
        self.request('/api/v3/client-aliases',self.admin,status=403,extra_headers={'X-Portal-Company':'2'})

    def test_today_dashboard_has_company_date_volume_finance_and_open_invoice_counts(self):
        work=self.work()
        self.post('invoices',dict(work_ids=[work['id']],due_at='2020-01-01'))
        today=datetime.fromisoformat(self.get('today')['data']['date']).date()
        closed_payroll=None
        expected_month_quantity=2
        expected_month_finance=(1000,400)
        if today.day>15:
            start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
            with portal.tenants.company_scope(1),portal.db() as conn:
                historical=dict(Repository(conn,1).get('works',work['id']),
                                completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
                for key in ('id','company_id'):historical.pop(key,None)
                Repository(conn,1).insert('works',historical)
                conn.commit()
            period=self.post('payroll-periods',dict(period_start=start,period_end=end))['data']
            employee=period['snapshot']['employees'][0]['employee_id']
            self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=employee,
                entry_type='payout',amount='1.00',reason='Dashboard test',request_id='dashboard-paid-once'))
            closed_payroll=(400,100,300)
            expected_month_quantity=4
            expected_month_finance=(2000,800)
        with portal.tenants.company_scope(1),portal.db() as conn:
            dashboard_repo=Repository(conn,1)
            dashboard_user=next(user for user in dashboard_repo.catalog('users') if user['id']==self.admin_id)
            Production(dashboard_repo,dashboard_user).today()
        data=self.get('today')['data']
        self.assertEqual(data['today_quantity'],2)
        self.assertEqual(data['month_quantity'],expected_month_quantity)
        self.assertEqual(data['today_finance'],dict(revenue=1000,salary=400))
        self.assertEqual((data['month_finance']['revenue'],data['month_finance']['salary']),expected_month_finance)
        self.assertEqual(data['today_productivity']['units'],2)
        self.assertIsNone(data['today_productivity']['units_per_hour'])
        self.assertEqual((data['open_invoice_count'],data['overdue_invoice_count'],data['overdue_debt']),(1,1,1000))
        self.assertIsNone(data['expected_profit'])
        if closed_payroll is None:self.assertIsNone(data['closed_month_payroll'])
        else:self.assertEqual((data['closed_month_payroll']['accrued'],data['closed_month_payroll']['paid'],data['closed_month_payroll']['balance']),closed_payroll)

    def test_today_control_channels_are_live_and_document_errors_persist_safely(self):
        work=self.work()
        first=self.get('today')['data']
        channels={item['id']:item for item in first['control_channels']}
        self.assertTrue({'material_low','payment_late','not_invoiced','payroll_period','document_error'} <= set(channels))
        self.assertEqual(channels['not_invoiced']['status'],'warning')
        self.assertGreater(channels['not_invoiced']['amount'],0)
        invoice=self.post('invoices',dict(work_ids=[work['id']],due_at='2020-01-01'))['data']
        second=self.get('today')['data'];channels={item['id']:item for item in second['control_channels']}
        self.assertEqual(channels['not_invoiced']['status'],'ok')
        self.assertEqual(channels['payment_late']['status'],'warning')
        self.assertGreater(channels['payment_late']['amount'],0)

        body={'document_type':'not-a-real-document-type','request_id':'document-error-once'}
        self.post('document-generate',body,status=400)
        self.post('document-generate',body,status=400)
        third=self.get('today')['data'];channels={item['id']:item for item in third['control_channels']}
        self.assertEqual(channels['document_error']['status'],'critical')
        self.assertEqual(channels['document_error']['count'],1)
        self.assertTrue(any(item.get('type')=='document_error' for item in third['attention']))
        self.post('document-generate',body,self.worker,status=403)
        recovered=self.post('document-generate',{'document_type':'invoice_pdf','invoice_id':invoice['id'],
            'request_id':'document-recovered-once'})['data']
        self.assertEqual(recovered['status'],'ready')
        fourth=self.get('today')['data'];channels={item['id']:item for item in fourth['control_channels']}
        self.assertEqual(channels['document_error']['status'],'ok')
        self.assertEqual(channels['document_error']['count'],0)
        with portal.tenants.company_scope(1),portal.db() as conn:
            events=Repository(conn,1).list('notifications')
        rows=[row for row in events if row.get('event')=='document_error']
        self.assertEqual(len(rows),1)
        self.assertEqual(set(rows[0]) & {'error','message','exception','traceback'},set())
        self.assertEqual(len([row for row in events if row.get('event')=='document_recovered']),1)

    def test_payroll_control_channel_marks_finished_half_month_ready_then_closed(self):
        current=self.work()
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            historical=dict(repo.get('works',current['id']),completed_at='2026-10-10T12:00:00.000000',
                            created_at='2026-10-10T12:00:00.000000')
            for key in ('id','company_id'):historical.pop(key,None)
            repo.insert('works',historical)
            admin_user=next(user for user in repo.catalog('users') if user['id']==self.admin_id)
            fixed=Production(repo,admin_user,lambda:'2026-10-16T10:00:00.000000')
            before={item['id']:item for item in fixed.today()['control_channels']}['payroll_period']
            self.assertEqual((before['period_start'],before['period_end']),('2026-10-01','2026-10-15'))
            self.assertEqual(before['status'],'warning')
            closed=fixed.payroll_period({'period_start':'2026-10-01','period_end':'2026-10-15'})
            conn.commit()
            after={item['id']:item for item in fixed.today()['control_channels']}['payroll_period']
        self.assertEqual(closed['status'],'closed')
        self.assertEqual(after['status'],'ok')
        self.assertTrue(after['closed'])

    def test_chat_stickers_absence_validation_idempotency_and_tenant_scope(self):
        self.assertEqual([item['key'] for item in self.get('chat-sticker-catalog')['data']],
                         ['accepted','in_progress','done','help','important','thanks'])
        for key in ('accepted','in_progress','done','help','important','thanks'):
            item=self.post('chat',dict(subtype='sticker',sticker_key=key))['data']
            self.assertEqual((item['message_type'],item['sticker_key']),('sticker',key))
        self.post('chat',dict(subtype='sticker',sticker_key='../x'),status=400)
        self.post('chat',dict(subtype='sticker',sticker_key='hello'),status=400)
        self.post('chat',dict(subtype='sticker',sticker_key='not-in-catalog'),status=400)
        self.post('chat',dict(subtype='sticker',sticker_key='accepted',recipient_user_id=self.worker_id),status=400)
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
        self.request('/api/v3/invitations?status=all',manager,status=403)
        self.request('/api/v3/invitations',manager,body,method='POST',status=403)
        director=self.role_token('director')
        body['username']='director-invite';body['request_id']='director-invite'
        director_invite=self.request('/api/v3/invitations',director,body,method='POST')['data']
        self.request('/api/v3/invitations',director,body,method='POST',extra_headers={'X-Portal-Company':'2'},status=403)
        director_invite_id=director_invite['invite']['id']
        self.request('/api/v3/invitations',manager,{'action':'approve','invite_id':director_invite_id},method='POST',status=403)
        self.request('/api/v3/invitations',manager,{'action':'revoke','invite_id':director_invite_id},method='POST',status=403)
        revoked=self.request('/api/v3/invitations',director,{'action':'revoke','invite_id':director_invite_id},method='POST')['data']
        revoke_replay=self.request('/api/v3/invitations',director,{'action':'revoke','invite_id':director_invite_id},method='POST')['data']
        self.assertEqual((revoked['status'],revoke_replay['status']),('revoked','revoked'))
        self.request('/api/access-invites/accept',body={'token':director_invite['token'],'pin':'6789'},method='POST',status=403)
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
        self.post('settings',dict(monday_time='11:30',utc_offset_minutes=240,
                                 reminder_enabled=True,reminder_cadence='weekly'))
        self.assertEqual(self.get('settings')['data']['reminder_cadence'],'weekly')
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
        self.assertEqual(events['company.settings.updated']['fields'],
                         ['monday_time','reminder_cadence','reminder_enabled','utc_offset_minutes'])
        self.assertEqual(events['user.permissions.updated']['fields'],['work.write'])
        allowed={'actor_id','company_id','created_at','entity_id','event','fields','id'}
        self.assertEqual(set(events['company.settings.updated']),allowed)
        self.assertEqual(set(events['user.permissions.updated']),allowed)
        # Audit timestamps can legitimately contain strings such as "11:30".
        # Check only the event payload fields that could leak changed values.
        safe_events={name:{key:value for key,value in event.items()
                           if key not in ('id','created_at')}
                     for name,event in events.items()}
        serialized=json.dumps(safe_events,ensure_ascii=False)
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

    def test_first_tariff_can_be_created_when_operation_has_no_history(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            now=utcnow()
            cursor=conn.execute("INSERT INTO portal_client_operations(client_id,name,employee_rate,client_rate,active,sort_order,created_at,updated_at) VALUES(?,?,?,?,1,0,?,?)",
                                (1,'Операция без тарифа',0,0,now,now))
            operation_id=cursor.lastrowid
            conn.commit()
        self.assertEqual(self.get('tariff-history?operation_id='+str(operation_id))['data'],[])
        self.post('tariffs',dict(client_id=1,operation_id=operation_id,employee_rate=1),status=400)
        created=self.post('tariffs',dict(client_id=1,operation_id=operation_id,employee_rate=1,client_rate=2))['data']
        self.assertEqual((created['employee_rate'],created['client_rate']),(100,200))
        history=self.get('tariff-history?operation_id='+str(operation_id))['data']
        self.assertEqual(len(history),1)
        self.assertEqual((history[0]['employee_rate'],history[0]['client_rate']),(100,200))

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
        bulk=self.get('tariff-history')['data']
        self.assertEqual([row for row in bulk if row['operation_id']==1],history)
        self.assertEqual(len(history),3)
        self.assertEqual(history[0]['employee_rate'],9900)
        self.assertEqual(history[-1]['employee_rate'],200)
        self.get('tariff-history?operation_id=1&company_id=2',status=403)
        self.post('permissions',dict(user_id=self.worker_id,permissions={'rates.client':True}))
        manager_history=self.get('tariff-history?operation_id=1',self.worker)['data']
        self.assertNotIn('employee_rate',manager_history[0])
        self.assertIn('client_rate',manager_history[0])
        client_future=(datetime.utcnow()+timedelta(days=2)).isoformat()
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=7,effective_from=client_future),self.worker,status=403)
        client_body=dict(client_id=1,operation_id=1,client_rate=7,effective_from=client_future,request_id='tariff-client-only-idempotent')
        client_version=self.post('tariffs',client_body,self.worker)['data']
        client_replay=self.post('tariffs',client_body,self.worker)['data']
        self.assertEqual(client_version['client_rate'],700)
        self.assertEqual(client_replay['id'],client_version['id'])
        self.assertNotIn('employee_rate',client_version)
        self.assertNotIn('employee_rate',client_replay)
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
        self.assertEqual(economy['plan'],dict(salary=2000,revenue=5000,materials=4000,other=0,profit=-1000,volume=10))
        self.assertEqual(economy['fact'],dict(salary=400,revenue=1000,materials=800,other=0,profit=-200,volume=2))
        self.assertEqual(economy['deviation'],dict(salary=-1600,revenue=-4000,materials=-3200,other=0,profit=800,volume=-8))
        self.assertEqual(economy['margin_bps'],dict(plan=-2000,fact=-2000,deviation=0))
        self.assertEqual((economy['finished_units'],economy['cost_per_unit'],economy['profit_per_unit']),(2,600,-100))
        self.post('usage',dict(work_id=w['id'],material_id=1,quantity=1))
        self.post('expenses',dict(batch_id=b['id'],amount=1,category='Доставка'))
        e=self.get('economy?batch_id='+b['id'])['data']
        self.assertEqual(e['fact'],dict(salary=400,revenue=1000,materials=1000,other=100,profit=-500,volume=2))
        self.assertEqual(e['deviation'],dict(salary=-1600,revenue=-4000,materials=-3000,other=100,profit=500,volume=-8))
        self.assertEqual(e['margin_bps'],dict(plan=-2000,fact=-5000,deviation=-3000))
        self.assertEqual((e['cost_per_unit'],e['profit_per_unit']),(750,-250))
        finance=self.get('finance')['data']['clients'][0];self.assertEqual(finance['profit'],-500)
        self.get('finance',self.worker,status=403)

    def test_task_plan_other_cost_requires_finance_read_capability(self):
        batch=self.batch()
        manager=self.role_token('manager')
        # Tasks may be delegated to a worker, but creating an explicit financial
        # plan cost still requires the finance capability.
        body=dict(batch_id=batch['id'],operation_id=1,quantity=10,assignees=[self.worker_id],other_cost='1.25')
        self.request('/api/v3/tasks',manager,dict(body,request_id='manager-plan-cost-forbidden'),method='POST',status=403)
        with portal.tenants.company_scope(1),portal.db() as conn:
            repository=Repository(conn,1)
            self.assertFalse(any(task['batch_id']==batch['id'] for task in repository.list('tasks')))
        director=self.role_token('director')
        created=self.request('/api/v3/tasks',director,dict(body,request_id='director-plan-cost-allowed'),method='POST')['data']
        economy=self.get('economy?batch_id='+batch['id'],director)['data']
        self.assertEqual(economy['plan']['other'],125)
        self.assertEqual(created['batch_id'],batch['id'])

    def test_batch_economy_marks_missing_plan_unavailable_instead_of_zero(self):
        batch=self.batch()
        economy=self.get('economy?batch_id='+batch['id'])['data']
        for key in ('salary','revenue','materials','other','profit','volume'):
            self.assertIsNone(economy['plan'][key],key)
            self.assertIsNone(economy['deviation'][key],key)
        self.assertIsNone(economy['margin_bps']['plan'])
        self.assertIsNone(economy['margin_bps']['deviation'])
        self.assertEqual(economy['fact']['volume'],0)
        self.assertEqual(economy['fact']['profit'],0)

    def test_margin_basis_points_use_integer_rounding_and_zero_revenue_is_unavailable(self):
        from production_service import margin_basis_points
        self.assertEqual(margin_basis_points(1,3),3333)
        self.assertEqual(margin_basis_points(-1,3),-3333)
        self.assertEqual(margin_basis_points(1,20000),1)
        self.assertEqual(margin_basis_points(-1,20000),-1)
        self.assertIsNone(margin_basis_points(0,0))

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
        from production_service import margin_basis_points
        self.assertEqual(data['clients'][0]['profit'],base)
        self.assertEqual(data['company_overhead'],1000)
        self.assertEqual(data['net_profit'],base-1000)
        self.assertEqual(data['totals'],{key:sum(row[key] for row in data['clients']) for key in ('revenue','salary','materials','other')})
        self.assertEqual(data['clients'][0]['margin_bps'],margin_basis_points(data['clients'][0]['profit'],data['clients'][0]['revenue']))
        self.assertEqual(data['client_margin_bps'],margin_basis_points(data['client_profit'],data['totals']['revenue']))
        self.assertEqual(data['net_margin_bps'],margin_basis_points(data['net_profit'],data['totals']['revenue']))
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

    def test_receivables_aging_ignores_unlinked_legacy_invoice_rows(self):
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            repo.insert('invoices',dict(amount=900,due_at='2020-01-01',work_ids=[],lines=[]),
                        'unlinked-legacy-aging-invoice')
            conn.commit()
            admin_user=next(item for item in repo.catalog('users') if item['id']==self.admin_id)
            report=Production(repo,admin_user,clock=lambda:'2026-09-30T12:00:00').receivables(
                {'page':['1'],'limit':['100']})
        self.assertEqual((report['total'],report['outstanding'],report['overdue']), (0,0,0))
        self.assertEqual(report['items'],[])

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
        self.assertTrue(data['groups'][0]['user_name']);self.assertTrue(data['groups'][0]['client_name']);self.assertTrue(data['groups'][0]['operation_name'])
        self.assertEqual(data['quality'],dict(available=False,recorded_units=0,defects=None));self.assertEqual(data['batch_groups'],[])
        b=self.batch();t=self.task(b)
        self.post('work',dict(task_id=t['id'],quantity=2,started_at=(datetime.utcnow()-timedelta(hours=1)).isoformat()),self.worker)
        updated=self.get('analytics',self.worker)['data'];forecast=updated['forecasts'][0]
        batch_group=next(group for group in updated['batch_groups'] if group['batch_id']==b['id'] and group['operation_id']==1)
        self.assertEqual(batch_group['client_id'],1);self.assertTrue(batch_group['batch_number']);self.assertGreater(batch_group['units_per_hour'],0)
        self.assertGreater(forecast['units_per_hour'],0);self.assertIsNotNone(forecast['estimated_completion'])

    def test_analytics_manager_sees_team_only_for_assigned_clients(self):
        manager=self.role_token('manager');manager_user=self.request('/api/me',manager)['user']
        with portal.tenants.company_scope(1),portal.db() as conn:
            legacy_id=conn.execute('SELECT telegram_id FROM app_users WHERE id=?',(manager_user['id'],)).fetchone()[0]
            conn.execute('INSERT INTO manager_client_assignments(telegram_id,client_id,active) VALUES(?,1,1)',(legacy_id,))
            conn.commit()
            hidden_client=portal.save_client({'name':'Analytics unassigned client'})
            hidden_operation=portal.save_operation({'name':'Hidden operation','employee_rate':2,'client_rate':5},hidden_client)
        self.work()
        self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.admin)
        self.post('work',dict(client_id=hidden_client,operation_id=hidden_operation,quantity=3),self.worker)

        team=self.get('analytics',manager)['data']
        self.assertEqual({group['user_id'] for group in team['groups'] if group['client_id']==1},{self.worker_id,self.admin_id})
        self.assertNotIn(hidden_client,{group['client_id'] for group in team['groups']})
        self.assertTrue(all(group['client_name']=='Client' and group['operation_name']=='Packing'
                            for group in team['groups']))
        self.assertEqual(team['quality'],dict(available=False,recorded_units=0,defects=None))

        self_only=self.get('analytics',self.worker)['data']
        self.assertEqual({group['user_id'] for group in self_only['groups']},{self.worker_id})
        self.assertEqual(sum(group['quantity'] for group in self_only['groups']),5)

    def test_analytics_period_comparison_uses_company_dates_and_valid_timing_only(self):
        previous_work_date=datetime.now().date()+timedelta(days=30)
        current_start=previous_work_date+timedelta(days=5)
        current_end=current_start+timedelta(days=6)
        current_work_date=current_start+timedelta(days=2)
        previous_start=current_start-timedelta(days=7)
        previous_end=current_start-timedelta(days=1)
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1);worker=next(user for user in repo.catalog('users') if user['id']==self.worker_id)
            previous_clock=previous_work_date.isoformat()+'T12:00:00.000000'
            current_clock=current_work_date.isoformat()+'T12:00:00.000000'
            current_started=current_work_date.isoformat()+'T11:00:00.000000'
            Production(repo,worker,lambda:previous_clock).work(
                dict(client_id=1,operation_id=1,quantity=1))
            Production(repo,worker,lambda:current_clock).work(
                dict(client_id=1,operation_id=1,quantity=2,started_at=current_started))
            conn.commit()
        data=self.get(f'analytics?from={current_start.isoformat()}&to={current_end.isoformat()}',self.worker)['data']
        comparison=data['comparison']
        self.assertEqual((comparison['previous_start'],comparison['previous_end']),
                         (previous_start.isoformat(),previous_end.isoformat()))
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
        defaults=self.get('settings',director)['data']
        self.assertEqual(defaults['monday_time'],'10:00')
        self.assertEqual((defaults['reminder_enabled'],defaults['reminder_cadence']),(False,'daily'))
        self.post('settings',dict(monday_time='11:00',wednesday_time='12:00',utc_offset_minutes=0,
                                  reminder_enabled=True,reminder_cadence='weekly'),director)
        configured=self.get('settings',director)['data']
        self.assertEqual((configured['reminder_enabled'],configured['reminder_cadence']),(True,'weekly'))
        self.post('settings',dict(reminder_enabled='true'),director,status=400)
        self.post('settings',dict(reminder_cadence='hourly'),director,status=400)
        self.get('settings',manager,status=403)
        self.post('settings',dict(monday_time='09:00'),manager,status=403)
        self.get('audit',manager,status=403)
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
        today=datetime.fromisoformat(self.get('today')['data']['date']).date()
        historical_month=(today-timedelta(days=60)).replace(day=1)
        start=historical_month.isoformat();end=historical_month.replace(day=15).isoformat()
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
        # Packer has no chat access by default in the current role matrix; grant it explicitly
        # here because this test covers chat mechanics rather than role defaults.
        self.post('permissions',dict(user_id=self.worker_id,permissions={'chat.read':True,'chat.write':True}))
        other_worker_id=self.request('/api/me',self.other_worker)['user']['id']
        self.post('permissions',dict(user_id=other_worker_id,permissions={'chat.read':True,'chat.write':True}),self.other_admin)
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
            for index in range(1000):
                r.insert('chat_messages',dict(room='general',sender_user_id=self.worker_id,sender_name='Новый',
                    text=f'Сообщение {index}',created_at=f'2026-10-02T12:{index//60:02d}:{index%60:02d}.000000'))
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
        self.post('permissions',dict(user_id=self.worker_id,permissions={'chat.read':True,'chat.write':True}))
        result=self.request('/api/v3/batches',self.admin,{'request_id':'oversize','client_id':1,'product':'X','quantity':1,'comment':'x'*70000},status=400)
        self.assertIn('64',result['error'])
        payload=b'a'*70000
        sent=self.post('chat',dict(text='Большой файл',attachment={'name':'a.txt','mime_type':'text/plain','file_b64':base64.b64encode(payload).decode('ascii')}),self.worker)['data']
        self.assertEqual(sent['attachment']['size_bytes'],len(payload))

    def test_chat_attachment_security_hash_and_retention(self):
        self.post('permissions',dict(user_id=self.worker_id,permissions={'chat.read':True,'chat.write':True}))
        other_worker_id=self.request('/api/me',self.other_worker)['user']['id']
        self.post('permissions',dict(user_id=other_worker_id,permissions={'chat.read':True}),self.other_admin)
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
            for index in range(1000):
                r.insert('chat_messages',dict(room='general',sender_user_id=self.worker_id,sender_name='Новый',
                    text=f'Сообщение {index}',created_at=f'2026-10-02T13:{index//60:02d}:{index%60:02d}.000000'))
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
        self.assertEqual(result['company']['id'],1)
        self.assertIn('module_toggles',result['company'])
        self.assertTrue(result['server_time'])
        self.request('/api/v3/work',self.owner,dict(request_id='owner-work',client_id=1,operation_id=1,quantity=1),status=400,extra_headers={'X-Portal-Company':'1'})

    def test_personal_messenger_is_owner_only_secret_free_and_role_restricted(self):
        account=self.post('messenger',dict(mode='create_account',platform='telegram',label='Рабочий Telegram'),self.worker)['data']
        self.assertEqual((account['owner_user_id'],account['account_type'],account['connection_state']),
                         (self.request('/api/me',self.worker)['user']['id'],'personal_work','adapter_unconfigured'))
        self.assertEqual(self.get('messenger',self.worker)['data']['accounts'][0]['id'],account['id'])
        self.post('messenger',dict(mode='create_conversation',account_id=account['id'],title='Рабочая беседа'),self.worker)
        self.assertEqual(self.get('messenger',self.worker)['data']['conversations'][0]['title'],'Рабочая беседа')
        self.get('messenger',self.role_token('manager'),status=403)
        self.get('messenger',self.role_token('director'),status=403)
        self.post('messenger',dict(mode='create_account',platform='max',label='bad',password='invented'),self.worker,status=400)
        self.assertEqual(len(self.get('messenger',self.worker)['data']['accounts']),1)
        self.assertEqual(self.get('messenger',self.other_admin)['data']['accounts'],[])

    def test_messenger_relay_ticket_is_short_lived_secret_free_and_role_restricted(self):
        env={'PORTAL_MESSENGER_RELAY_URL':'https://relay.vart-portal.ru:9443',
             'PORTAL_MESSENGER_RELAY_SECRET':'test-secret-'+'x'*40,
             'PORTAL_MESSENGER_RELAY_TTL_SECONDS':'600'}
        with patch.dict('os.environ',env,clear=False):
            ticket=self.get('messenger-relay-ticket',self.worker)['data']
            self.assertTrue(ticket['enabled'])
            self.assertEqual(ticket['proxy_url'],'https://relay.vart-portal.ru:9443')
            self.assertEqual(ticket['realm'],'PORTAL Messenger Relay')
            self.assertTrue(ticket['username'].startswith('v2.telegram.'))
            self.assertEqual(ticket['provider'],'telegram')
            self.assertFalse(ticket['required'])
            self.assertGreater(len(ticket['password']),30)
            self.assertNotIn('PORTAL_MESSENGER_RELAY_SECRET',ticket)
            self.get('messenger-relay-ticket',self.role_token('manager'),status=403)
            self.get('messenger-relay-ticket',self.role_token('director'),status=403)
        with patch.dict('os.environ',{'PORTAL_TELEGRAM_RELAY_REQUIRED':'true'},clear=False):
            os.environ.pop('PORTAL_MESSENGER_RELAY_URL',None)
            os.environ.pop('PORTAL_MESSENGER_RELAY_SECRET',None)
            unavailable=self.get('messenger-relay-ticket',self.worker)['data']
            self.assertEqual(unavailable,{'provider':'telegram','enabled':False,'required':True})
        with patch.dict('os.environ',{'PORTAL_TELEGRAM_RELAY_REQUIRED':'maybe'},clear=False):
            os.environ.pop('PORTAL_MESSENGER_RELAY_URL',None)
            os.environ.pop('PORTAL_MESSENGER_RELAY_SECRET',None)
            unknown=self.get('messenger-relay-ticket',self.worker)['data']
            self.assertEqual(unknown,{'provider':'telegram','enabled':False,'required':False})

    def test_notification_center_read_receipt_is_per_user_and_tenant(self):
        batch=self.batch();task=self.task(batch)
        user_id=self.request('/api/me',self.worker)['user']['id']
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1)
            repo.insert('organizer_tasks',dict(assignee_user_id=user_id,created_by=user_id,title='Своя задача',
                due_at='2026-10-06T12:00:00',status='new',priority='normal',recurrence='none'))
            conn.commit()
        before=self.get('notification-centers',self.worker)['data']
        task_center=next(center for center in before if center['center']=='TASKS')
        self.assertEqual(task_center['unread_count'],1)
        task_item=task_center['items'][0]
        self.post('notification-read',dict(center='TASKS',item_id=task_item['id']),self.worker)
        after=self.get('notification-centers',self.worker)['data']
        self.assertEqual(next(center for center in after if center['center']=='TASKS')['unread_count'],0)
        self.get('notification-centers',self.other_admin)
        with portal.tenants.company_scope(1),portal.db() as conn:
            own=Repository(conn,1).get('notification_reads',f'{user_id}:TASKS:{task_item["id"]}')
        self.assertEqual(own['user_id'],user_id)

    def test_desktop_organizer_hierarchy_recurrence_and_company_isolation(self):
        director=self.role_token('director');manager=self.role_token('manager')
        with portal.tenants.company_scope(1):
            manager2_id=portal.save_user({'username':'manager2','pin':'4321','role':'manager'})
            with portal.db() as conn:manager2=portal.create_session(conn,manager2_id)
        director_id=self.request('/api/me',director)['user']['id']
        manager_id=self.request('/api/me',manager)['user']['id']
        due=(datetime.now()+timedelta(days=2)).replace(second=0,microsecond=0).isoformat(timespec='minutes')
        remind=(datetime.now()+timedelta(days=1)).replace(second=0,microsecond=0).isoformat(timespec='minutes')

        users=self.get('organizer-users',director)['data']
        self.assertEqual({u['role'] for u in users},{'director','admin','manager'})
        to_admin=self.post('organizer',dict(mode='create',assignee_user_id=self.admin_id,title='Проверить оплату',
            due_at=due,remind_at=remind,priority='important',repeat_rule='daily'),director)['data']
        self.assertEqual((to_admin['created_by'],to_admin['assignee_user_id']),(director_id,self.admin_id))
        self.post('organizer',dict(mode='create',assignee_user_id=manager2_id,title='Задача менеджеру',due_at=due),self.admin)
        self.post('organizer',dict(mode='create',assignee_user_id=manager2_id,title='Коллеге',due_at=due),manager)
        self.post('organizer',dict(mode='create',assignee_user_id=self.admin_id,title='Наверх нельзя',due_at=due),manager,status=403)
        self.post('organizer',dict(mode='create',assignee_user_id=director_id,title='Наверх нельзя',due_at=due),self.admin,status=403)

        overdue_due=(datetime.now()-timedelta(days=2)).replace(second=0,microsecond=0).isoformat(timespec='minutes')
        overdue=self.post('organizer',dict(mode='create',assignee_user_id=self.admin_id,title='Просроченная задача',
            due_at=overdue_due,priority='urgent'),director)['data']
        incoming=self.get('organizer?scope=incoming',self.admin)['data']
        overdue_visible=next(t for t in incoming if t['id']==overdue['id'])
        self.assertEqual(overdue_visible['status'],'new')
        self.assertEqual(overdue_visible['due_at'],overdue_due)
        task=next(t for t in incoming if t['id']==to_admin['id'])
        self.assertTrue(task['can_change_status']);self.assertFalse(task['can_edit']);self.assertTrue(task['can_comment'])
        creator_view=next(t for t in self.get('organizer?scope=assigned_by_me',director)['data'] if t['id']==task['id'])
        self.assertFalse(creator_view['can_comment'])
        self.post('organizer',dict(mode='comment',task_id=task['id'],comment='Начал выполнение, ожидаю подтверждение'),self.admin)
        self.post('organizer',dict(mode='comment',task_id=task['id'],comment='Комментарий не исполнителя'),director,status=403)
        self.post('organizer',dict(mode='comment',task_id=task['id'],comment=''),self.admin,status=400)
        self.post('organizer',dict(mode='status',task_id=task['id'],status='done',comment='Выполнено, результат проверен'),self.admin)
        events=self.get('organizer-events?task_id='+task['id'],self.admin)['data']
        comments=[e['detail'] for e in events if e['event']=='comment']
        self.assertIn('Начал выполнение, ожидаю подтверждение',comments)
        self.assertIn('Выполнено, результат проверен',comments)
        completed=next(t for t in self.get('organizer?scope=incoming',self.admin)['data'] if t['id']==task['id'])
        self.assertEqual(completed['status'],'done');self.assertTrue(completed['completed_at'])
        repeated=[t for t in self.get('organizer?scope=incoming',self.admin)['data'] if t.get('recurrence_of')==task['id']]
        self.assertEqual(len(repeated),1);self.assertEqual(repeated[0]['created_by'],director_id)

        peer=self.get('organizer?scope=incoming',manager2)['data']
        self.assertTrue(any(t['created_by']==manager_id for t in peer))
        self.get('organizer',self.worker,status=403)
        other=self.post('organizer',dict(mode='create',assignee_user_id=self.request('/api/me',self.other_admin)['user']['id'],
            title='Чужая компания',due_at=due),self.other_admin)['data']
        self.assertNotIn(other['id'],{t['id'] for t in self.get('organizer?scope=company',director)['data']})

    def test_organizer_bootstrap_returns_task_first_screen_payload(self):
        director=self.role_token('director')
        director_id=self.request('/api/me',director)['user']['id']
        due=(datetime.now()+timedelta(days=2)).replace(second=0,microsecond=0).isoformat(timespec='minutes')
        task=self.post('organizer',dict(mode='create',assignee_user_id=self.admin_id,
            title='Bootstrap задача',due_at=due,priority='important'),director)['data']
        payload=self.get('organizer-bootstrap',director)['data']
        self.assertIn(task['id'],{row['id'] for row in payload['tasks']})
        self.assertTrue(any(row['id']==director_id for row in payload['users']))
        self.assertTrue(payload['directors'])
        self.assertTrue(payload['responsibles'])
        self.assertIn('mine_requests',payload);self.assertIn('incoming_requests',payload)
        self.assertTrue(payload['synced_at'])
        self.get('organizer-bootstrap',self.worker,status=403)

    def test_organizer_director_requests_workflow_security_and_task_link(self):
        director=self.role_token('director');manager=self.role_token('manager')
        director_id=self.request('/api/me',director)['user']['id']
        with portal.tenants.company_scope(self.other):
            other_director_id=portal.save_user({'username':'other_director','pin':'9876','role':'director'})
            with portal.db() as conn:other_director=portal.create_session(conn,other_director_id)
        due=(datetime.now()+timedelta(days=3)).replace(second=0,microsecond=0).isoformat(timespec='minutes')
        attachment={'name':'material.png','mime_type':'image/png',
                    'file_b64':base64.b64encode(b'not-real-image-but-safe-test-bytes').decode('ascii')}
        created=self.post('organizer-requests',dict(mode='create',request_type='materials_purchase',
            director_user_id=director_id,title='Закупить вакуумные пакеты',description='Нужен запас на неделю',
            priority='urgent',requested_due_at=due,amount='1250.50',item_name='Вакуумный пакет 25x30',
            quantity='10.5',unit='уп.',initial_comment='Закупить до пятницы',attachment=attachment),manager)['data']
        self.assertEqual(created['status'],'new')
        self.assertEqual(created['amount'],125050)
        self.assertEqual(created['quantity'],'10.5')
        self.assertEqual(len(created['attachments']),1)
        request_id=created['id'];attachment_id=created['attachments'][0]['id']
        self.post('organizer-requests',dict(mode='create_task',organizer_request_id=request_id,
            responsible_user_id=self.admin_id),director,status=400)

        # A director cannot create a request even if a permission override is present.
        self.post('permissions',dict(user_id=director_id,permissions={'organizer.request.create':True}))
        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=director_id,
            title='Запрос от директора'),director,status=403)
        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=director_id,
            title='Сумма с float',amount=12.5),manager,status=400)
        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=director_id,
            title='Сумма с лишней точностью',amount='12.501'),manager,status=400)

        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=director_id,
            title='Запрещено'),self.worker,status=403)
        # IDs are tenant-local in split PostgreSQL/SQLite fixtures; an ID not present as a director in this tenant must fail closed.
        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=999999,
            title='Чужой директор'),manager,status=403)
        self.post('organizer-requests',dict(mode='create',request_type='repair',director_user_id=director_id,
            title='Запрос управляющего'),self.admin)
        self.post('organizer-requests',dict(mode='create',request_type='other',director_user_id=director_id,
            title='Опасное вложение',attachment={'name':'../evil.txt','mime_type':'text/plain',
            'file_b64':base64.b64encode(b'x').decode('ascii')}),manager,status=400)

        mine=self.get('organizer-requests?scope=mine',manager)['data']
        self.assertIn(request_id,{row['id'] for row in mine})
        incoming=self.get('organizer-requests?scope=incoming',director)['data']
        self.assertIn(request_id,{row['id'] for row in incoming})
        self.assertNotIn(request_id,{row['id'] for row in self.get('organizer-requests?scope=incoming',other_director)['data']})
        self.get('organizer-requests?scope=mine',self.worker,status=403)

        self.post('organizer-requests',dict(mode='decide',organizer_request_id=request_id,status='review'),manager,status=403)
        self.post('organizer-requests',dict(mode='decide',organizer_request_id=request_id,status='review'),director)
        request_users=self.get('organizer-request-responsibles',director)['data']
        self.assertEqual({row['role'] for row in request_users},{'director','admin','manager'})
        needs=self.post('organizer-requests',dict(mode='decide',organizer_request_id=request_id,
            status='needs_info',comment='Уточните количество'),director)['data']
        self.assertEqual(needs['status'],'needs_info')
        replied=self.post('organizer-requests',dict(mode='comment',organizer_request_id=request_id,
            comment='Количество подтверждено'),manager)['data']
        self.assertEqual(replied['status'],'review')
        approved=self.post('organizer-requests',dict(mode='decide',organizer_request_id=request_id,
            status='approved',responsible_user_id=self.admin_id,comment='Одобрено'),director)['data']
        self.assertEqual(approved['responsible_user_id'],self.admin_id)

        task1=self.post('organizer-requests',dict(mode='create_task',organizer_request_id=request_id,
            responsible_user_id=self.admin_id),director)['data']
        task2=self.post('organizer-requests',dict(mode='create_task',organizer_request_id=request_id,
            responsible_user_id=self.admin_id),director)['data']
        self.assertEqual(task1['id'],task2['id'])
        self.assertEqual((task1['linked_type'],task1['linked_id']),('request',request_id))
        refreshed=next(row for row in self.get('organizer-requests?scope=incoming',director)['data'] if row['id']==request_id)
        self.assertEqual(refreshed['task_id'],task1['id'])
        done=self.post('organizer-requests',dict(mode='decide',organizer_request_id=request_id,status='done'),director)['data']
        self.assertEqual(done['status'],'done')

        downloaded=self.get('organizer-request-file?id='+attachment_id,manager)['data']
        self.assertEqual(base64.b64decode(downloaded['file_b64']),b'not-real-image-but-safe-test-bytes')
        self.get('organizer-request-file?id='+attachment_id,other_director,status=400)
        events=self.get('organizer-request-events?organizer_request_id='+request_id,manager)['data']
        self.assertTrue(any(row['event']=='created' for row in events))
        self.assertTrue(any(row['event']=='task_created' for row in events))
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1);event=repo.list('organizer_request_events')[0]
            with self.assertRaises(ValueError):repo.update('organizer_request_events',dict(event,detail='tamper'))
            attachment_row=repo.get('organizer_request_attachments',attachment_id)
            with self.assertRaises(ValueError):repo.update('organizer_request_attachments',dict(attachment_row,original_name='tampered.txt'))
