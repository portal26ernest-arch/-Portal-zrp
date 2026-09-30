"""Synthetic staged import: preview writes nothing; explicit apply is tested below."""
import base64
import hashlib
import io
import json
import sqlite3
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from unittest.mock import patch

import test_documents_api as fixtures
from excel_template import workbook
from portal_excel_workbook import NS,parse_template
from excel_import import ExcelImport
from employee_names import employee_name_key
from production_service import Production
from production_repository import Repository

portal=fixtures.portal

def change_zip(payload,part,transform):
    out=io.BytesIO()
    with ZipFile(io.BytesIO(payload)) as source,ZipFile(out,'w') as target:
        for name in source.namelist():target.writestr(name,transform(source.read(name)) if name==part else source.read(name))
    return out.getvalue()

class ImportAPITest(unittest.TestCase):
    request=fixtures.DocumentAPITest.request
    tearDown=fixtures.DocumentAPITest.tearDown
    setUp=fixtures.DocumentAPITest.setUp
    role_token=fixtures.DocumentAPITest.role_token
    post=fixtures.DocumentAPITest.post
    get=fixtures.DocumentAPITest.get

    def payload(self,values=None):return workbook(values or {})
    def body(self,payload):return dict(file_b64=base64.b64encode(payload).decode(),original_filename='PORTAL.xlsx')
    def preview(self,payload,token=None,status=200,headers=None):
        result=self.request('/api/v3/excel-import-preview',token or self.admin,self.body(payload),status=status,extra_headers=headers)
        return result.get('data',result)

    def database_hashes(self):
        paths=[Path(portal.DB_PATH),portal.tenants.platform_path(portal.DB_PATH),portal.tenants.tenant_path(portal.DB_PATH,self.other)]
        return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    def test_employee_name_aliases_prevent_ambiguous_import_without_rewriting_names(self):
        for alias,canonical in (('Борисенко','Борискин'),('Вартанян','Варданян'),('Вдовин','Вдовина'),
                                ('Шульгинова','Шульгина'),('Эленгатика','Элегантика'),('Корягин','Карягин'),
                                ('Коорягин','Карягин'),('Чотчаев','Чотчаева')):
            self.assertEqual(employee_name_key('Артем '+alias),employee_name_key('Артем '+canonical))
        self.assertEqual(employee_name_key('  АРТЕМ Вартанян  '),employee_name_key('Артем Варданян'))
        self.assertEqual(employee_name_key('Вартанян, Артем'),employee_name_key('Варданян, Артем'))
        with portal.db() as conn:
            employee=conn.execute('SELECT telegram_id FROM employees WHERE company_id=1 ORDER BY telegram_id LIMIT 1').fetchone()
            conn.execute('UPDATE employees SET full_name=? WHERE company_id=1 AND telegram_id=?',('Артем Варданян',employee[0]))
            conn.commit()
        plan=self.preview(self.payload({'Сотрудники':[dict(employee_ref='alias-collision',full_name='Артем Вартанян')]}))
        self.assertIn('employee_identity_ambiguous',plan['rows'][0]['errors'])
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT full_name FROM employees WHERE company_id=1 AND telegram_id=?',(employee[0],)).fetchone()[0],'Артем Варданян')

    def test_employee_rename_history_is_stable_id_scoped_and_never_matches_by_fio(self):
        with portal.db() as conn:
            r=Repository(conn,1);employee=r.employee_catalog()[0]
            employee_id=employee['employee_id'];old_name=employee['full_name'];username=employee['username']
        new_name='Артем Варданян'
        payload=self.payload({'Сотрудники':[dict(employee_ref='stable-rename',employee_id=employee_id,
                                                full_name=new_name,profile_username=username)]})
        preview=self.preview(payload)
        self.assertEqual(preview['rows'][0]['classification'],'update')
        self.assertEqual(self.apply(payload,preview)['status'],'applied')
        with portal.db() as conn:
            r=Repository(conn,1);current={row['employee_id']:row for row in r.employee_catalog()}[employee_id]
            self.assertEqual(current['full_name'],new_name)
            history=[row for row in r.list('employee_name_history') if row['employee_id']==employee_id]
            aliases=[row for row in r.list('employee_aliases') if row['employee_id']==employee_id]
        self.assertEqual([(row['old_name'],row['new_name']) for row in history],[(old_name,new_name)])
        self.assertTrue(any(row['alias']==old_name and row['source']=='rename' for row in aliases))
        self.assertTrue(any(row['alias']=='Артем Вартанян' and row['source']=='knowledge' for row in aliases))
        self.assertEqual(self.get('employee-name-history?employee_id='+str(employee_id))['data'],history)
        self.assertEqual(self.get('employee-aliases?employee_id='+str(employee_id))['data'],aliases)
        self.assertEqual(self.get('employee-name-history',self.other_admin)['data'],[])
        self.get('employee-name-history',self.role_token('manager'),status=403)
        self.request('/api/v3/employee-aliases',self.admin,status=403,extra_headers={'X-Portal-Company':'2'})

    def test_preview_no_database_writes_for_admin_or_selected_owner(self):
        data={'Клиенты':[dict(client_ref='new',name='Синтетический клиент',active=1)],
              'Сотрудники':[dict(employee_ref='new',full_name='Синтетический сотрудник')],
              'Операции_Тарифы':[dict(client_ref='new',name='Операция',employee_rate='1.25',client_rate='3.50',active=1)]}
        payload=self.payload(data);before=self.database_hashes()
        plan=self.preview(payload)
        self.assertTrue(plan['can_apply']);self.assertEqual(plan['summary']['new'],3)
        self.assertEqual(self.database_hashes(),before)
        with patch('excel_import.LOG.info') as log:
            owner=self.preview(payload,self.owner,headers={'X-Portal-Company':'1'})
            self.assertTrue(owner['can_apply']);self.assertEqual(self.database_hashes(),before)
            self.assertNotIn('Синтетический сотрудник',str(log.call_args))
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_documents').fetchone()[0],0)

    def test_prefilled_template_is_unchanged_and_existing_client_update_is_previewed(self):
        payload=base64.b64decode(self.get('document-template')['data']['file_b64'])
        parsed=parse_template(payload);plan=self.preview(payload)
        self.assertTrue(plan['can_apply'],plan['summary'])
        self.assertEqual(plan['summary']['new']+plan['summary']['update'],0)
        data=parsed['rows'];data['Клиенты'][0]['name']='Переименованный'
        plan=self.preview(self.payload(data));self.assertEqual(plan['summary']['update'],1)
        self.assertEqual(self.get('catalog')['data']['clients'][0]['name'],'Client')

    def test_duplicates_employee_ambiguity_bad_role_money_status_date(self):
        cases=[({'Клиенты':[dict(client_ref='x',name='New'),dict(client_ref='x',name='Other')]},'invalid'),
               ({'Сотрудники':[dict(employee_ref='x',full_name='Worker One')]},'conflict'),
               ({'Сотрудники':[dict(employee_ref='x',full_name='New',role='owner')]},'invalid'),
               ({'Клиенты':[dict(client_ref='x',name='New',active='archived')]},'invalid'),
               ({'Клиенты':[dict(client_ref='x',name='New')],'Операции_Тарифы':[dict(client_ref='x',name='Op',employee_rate='NaN')]},'invalid'),
               ({'Клиенты':[dict(client_ref='x',name='New')],'Операции_Тарифы':[dict(client_ref='x',name='Op',employee_rate='1.001')]},'invalid'),
               ({'Клиенты':[dict(client_ref='x',name='New')],'Операции_Тарифы':[dict(client_ref='x',name='Op',employee_rate='1',effective_from='2026-99-99')]},'invalid')]
        for data,kind in cases:
            with self.subTest(kind=kind):
                plan=self.preview(self.payload(data));self.assertFalse(plan['can_apply']);self.assertGreater(plan['summary'][kind],0)

    def test_cross_company_sheet_ids_body_and_tokens(self):
        data={'Компания':[dict(company_id=self.other)],'Клиенты':[dict(client_ref='x',client_id=900,name='Foreign only')]}
        plan=self.preview(self.payload(data));self.assertFalse(plan['can_apply']);self.assertGreater(plan['summary']['invalid'],0)
        self.preview(self.payload(),headers={'X-Portal-Company':str(self.other)},status=403)
        self.request('/api/v3/excel-import-preview',self.admin,dict(self.body(self.payload()),company_id=self.other),status=403)
        self.preview(self.payload(),self.role_token('manager'),status=403)
        a=self.preview(self.payload());b=self.preview(self.payload(),self.other_admin)
        with portal.db() as conn:
            service=Production(Repository(conn,1),dict(id=self.admin_id,role='admin',company_id=1))
            importer=ExcelImport(service,None,{'name':'PORTAL'})
            with self.assertRaises(PermissionError):importer.verify(b['preview_token'])
            self.assertEqual(importer.verify(a['preview_token'])['company_id'],1)

    def test_tariff_overlap_backdate_unique_conflicts_and_ambiguous_client(self):
        base={'Клиенты':[dict(client_ref='c',client_id=1,name='Client')],
              'Операции_Тарифы':[dict(client_ref='c',client_id=1,operation_id=1,name='Packing',employee_rate='99',client_rate='5',effective_from='2020-01-01')]}
        self.assertGreater(self.preview(self.payload(base))['summary']['conflict'],0)
        future=(datetime.utcnow()+timedelta(days=3)).isoformat()
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=3,client_rate=6,effective_from=future))
        base['Операции_Тарифы'][0]['effective_from']=(datetime.utcnow()+timedelta(days=2)).isoformat()
        plan=self.preview(self.payload(base));self.assertIn('tariff_overlap_or_effective_conflict',plan['rows'][-1]['errors'])
        # Equal instants with differing timestamp precision must also conflict.
        future=(datetime.utcnow()+timedelta(days=4)).replace(microsecond=0).isoformat()
        self.post('tariffs',dict(client_id=1,operation_id=1,employee_rate=4,client_rate=7,effective_from=future))
        base['Операции_Тарифы'][0]['effective_from']=future+'.000000'
        self.assertIn('tariff_overlap_or_effective_conflict',self.preview(self.payload(base))['rows'][-1]['errors'])
        self.assertGreater(self.preview(self.payload({'Клиенты':[dict(client_ref='x',name='Client')]}))['summary']['conflict'],0)
        self.assertGreater(self.preview(self.payload({'Операции_Тарифы':[dict(client_ref='unknown',name='Op',employee_rate='1')]}))['summary']['invalid'],0)

    def test_invalid_workbook_version_sheets_headers_formulas_macros_and_limits(self):
        payload=self.payload()
        cases=[b'not ZIP',
               change_zip(payload,'xl/workbook.xml',lambda raw:raw.replace('Компания'.encode(),'Wrong'.encode())),
               change_zip(payload,'xl/worksheets/sheet1.xml',lambda raw:raw.replace(b'<t>1.0</t>',b'<t>99</t>')),
               change_zip(payload,'xl/worksheets/sheet2.xml',lambda raw:raw.replace(b'employee_id',b'bad_key')),
               change_zip(payload,'xl/worksheets/sheet2.xml',lambda raw:raw.replace(b'<c r="A1"',b'<c r="A1"').replace(b'<is><t>PORTAL_TEMPLATE_VERSION</t></is>',b'<f>1+1</f><v>2</v>')),
               change_zip(payload,'[Content_Types].xml',lambda raw:raw.replace(b'spreadsheetml.sheet.main',b'spreadsheetml.sheet.macroEnabled.main')),
               change_zip(payload,'xl/workbook.xml',lambda raw:raw.decode().encode('utf-16')),
               change_zip(payload,'xl/workbook.xml',lambda raw:b'<!DOCTYPE workbook [<!ENTITY injected "secret">]>'+raw),
               change_zip(payload,'xl/_rels/workbook.xml.rels',lambda raw:raw.replace(b'<Relationship ',b'<Relationship TargetMode="External" ',1)),
               self.payload({'Клиенты':[dict(client_ref=str(i),name='Row '+str(i)) for i in range(2001)]})]
        for value in cases:
            with self.subTest(size=len(value)):self.preview(value,status=400)

    def test_signed_confirmation_tamper_expiry_and_actor_binding(self):
        plan=self.preview(self.payload())
        with portal.db() as conn:
            service=Production(Repository(conn,1),dict(id=self.admin_id,role='admin',company_id=1))
            importer=ExcelImport(service,None,{'name':'PORTAL'})
            with self.assertRaises(ValueError):importer.verify(plan['preview_token'][:-1]+'!')
            with patch('excel_import.time.time',return_value=plan['expires_at']+1):
                with self.assertRaises(ValueError):importer.verify(plan['preview_token'])
            importer.u=dict(importer.u,id=self.admin_id+999)
            with self.assertRaises(PermissionError):importer.verify(plan['preview_token'])

    def apply(self,payload,preview=None,token=None,status=200,**extra):
        preview=preview or self.preview(payload,token)
        body=dict(self.body(payload),import_id=preview['import_id'],preview_token=preview['preview_token'],**extra)
        result=self.request('/api/v3/excel-import-apply',token or self.admin,body,status=status)
        return result.get('data',result)

    def new_catalog(self):
        return {'Компания':[dict(company_id=1,legal_name='Синтетическая организация',inn='0012345678')],
                'Сотрудники':[dict(employee_ref='new-person',full_name='Новый сотрудник',profile_username='profile-only')],
                'Клиенты':[dict(client_ref='new-client',name='Новый клиент',active=1,legal_name='Синтетический клиент',inn='0012345678')],
                'Операции_Тарифы':[dict(client_ref='new-client',name='Новая операция',employee_rate='10.25',client_rate='20.50',active=1)]}

    def test_existing_user_role_disable_revokes_sessions_and_keeps_profile_identity(self):
        target=self.role_token('shift')
        with portal.db() as conn:
            uid=conn.execute("SELECT id FROM app_users WHERE username='shift'").fetchone()[0]
            eid=Repository(conn,1).payroll_employee(101,legacy=True)['employee_id']
        payload=self.payload({'Сотрудники':[dict(employee_ref='existing',employee_id=eid,user_id=uid,full_name='Worker One',profile_username='one',role='packer',active=0)]})
        self.assertEqual(self.apply(payload)['status'],'applied')
        with portal.db() as conn:
            self.assertEqual(tuple(conn.execute('SELECT role,active,telegram_id FROM app_users WHERE id=?',(uid,)).fetchone()),('packer',0,101))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM app_sessions WHERE user_id=?',(uid,)).fetchone()[0],0)
            self.assertEqual(Repository(conn,1).payroll_employee(101,legacy=True)['employee_id'],eid)
        self.get('catalog',target,status=401)

    def test_access_activation_self_change_and_last_admin_are_rejected(self):
        target=self.role_token('shift')
        with portal.db() as conn:
            uid=conn.execute("SELECT id FROM app_users WHERE username='shift'").fetchone()[0]
            r=Repository(conn,1);eid=r.payroll_employee(101,legacy=True)['employee_id']
            conn.execute('UPDATE app_users SET active=0 WHERE id=?',(uid,))
            conn.execute('UPDATE app_users SET telegram_id=101 WHERE id=?',(self.admin_id,))
        row=dict(employee_ref='existing',employee_id=eid,user_id=uid,full_name='Worker One',profile_username='one',role='shift',active=1)
        plan=self.preview(self.payload({'Сотрудники':[row]}))
        self.assertIn('activation_requires_access_api',plan['rows'][0]['errors'])
        row.update(user_id=self.admin_id,role='packer',active=1)
        plan=self.preview(self.payload({'Сотрудники':[row]}))
        self.assertIn('own_access_change_requires_access_api',plan['rows'][0]['errors'])
        payload=self.payload({'Сотрудники':[row]})
        plan=self.preview(payload,self.owner,headers={'X-Portal-Company':'1'})
        self.assertIn('last_admin_conflict',plan['rows'][0]['errors'])

    def test_apply_after_preview_registers_results_audit_and_independent_employee_id(self):
        payload=self.payload(self.new_catalog());preview=self.preview(payload);result=self.apply(payload,preview)
        self.assertEqual(result['status'],'applied');self.assertEqual(result['result_counts']['new'],3)
        self.assertEqual(result['result_counts']['updated'],1)
        with portal.db() as conn:
            employee=conn.execute("SELECT i.employee_id,e.telegram_id FROM employees e JOIN payroll_employee_identities i ON i.company_id=e.company_id AND i.legacy_employee_id=e.telegram_id WHERE e.full_name='Новый сотрудник'").fetchone()
            self.assertGreater(employee[0],0);self.assertLess(employee[1],0);self.assertNotEqual(employee[0],employee[1])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users WHERE username='profile-only'").fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT inn FROM portal_company_requisites WHERE id=1').fetchone()[0],'0012345678')
            events=[json.loads(row[0])['event'] for row in conn.execute("SELECT payload FROM portal_production WHERE kind='audit'")]
            for event in ('import_preview_created','import_applied','document_generated'):self.assertIn(event,events)
        stored=self.get('excel-import-result?id='+result['import_id'])['data'];self.assertEqual(stored,result)
        report=json.loads(base64.b64decode(self.get('document-file?id='+result['result_document_id'])['data']['file_b64']))
        self.assertEqual(report['status'],'applied');self.assertNotIn('Новый сотрудник',json.dumps(report,ensure_ascii=False))
        self.get('excel-import-result?id='+result['import_id'],self.other_admin,status=400)

    def test_apply_retry_same_id_checksum_is_idempotent_even_after_state_changes(self):
        payload=self.payload(self.new_catalog());preview=self.preview(payload)
        a=self.apply(payload,preview);b=self.apply(payload,preview)
        self.assertEqual(a,b)
        self.assertEqual(self.apply(payload)['import_id'],a['import_id'])
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM portal_clients WHERE name='Новый клиент'").fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM portal_documents WHERE document_type='import_result'").fetchone()[0],1)

    def test_apply_requires_preview_exact_workbook_actor_and_unchanged_state(self):
        payload=self.payload({'Клиенты':[dict(client_ref='x',name='New')]});preview=self.preview(payload)
        self.request('/api/v3/excel-import-apply',self.admin,self.body(payload),status=400)
        altered=self.payload({'Клиенты':[dict(client_ref='x',name='Altered')]})
        self.apply(altered,preview,status=400)
        self.apply(payload,preview,self.other_admin,status=403)
        self.post('batches',dict(client_id=1,product='No catalog change',quantity=1))
        self.request('/api/admin/clients',self.admin,dict(name='Concurrent catalog edit'))
        self.apply(payload,preview,status=400)
        with portal.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0],0)

    def test_invalid_preview_apply_returns_failed_report_and_zero_catalog_changes(self):
        payload=self.payload({'Клиенты':[dict(client_ref='x',name='Valid new'),dict(client_ref='x',name='Duplicate')]})
        preview=self.preview(payload);result=self.apply(payload,preview,status=409)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['result_counts']['new'],0)
        self.assertIn('duplicate_client_reference',str(result['error_report']))
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM portal_clients WHERE name='Valid new'").fetchone()[0],0)

    def test_mid_apply_failure_rolls_back_catalogs_sessions_and_tariffs_then_can_retry(self):
        import excel_apply
        payload=self.payload(self.new_catalog());preview=self.preview(payload)
        with portal.db() as conn:
            before={table:conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('employees','payroll_employee_identities','portal_clients','portal_client_operations','portal_company_requisites','portal_client_requisites','app_sessions')}
            tariffs=conn.execute("SELECT COUNT(*) FROM portal_production WHERE kind='tariffs'").fetchone()[0]
        original=excel_apply._apply_row;calls=[]
        def fail(importer,row,refs):
            result=original(importer,row,refs);calls.append(row['sheet'])
            if len(calls)==3:raise RuntimeError('secret canary should never enter API/audit')
            return result
        with patch('excel_apply._apply_row',side_effect=fail):result=self.apply(payload,preview,status=409)
        self.assertEqual(result['status'],'failed');self.assertNotIn('secret canary',str(result))
        with portal.db() as conn:
            for table,count in before.items():self.assertEqual(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],count,table)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM portal_production WHERE kind='tariffs'").fetchone()[0],tariffs)
            self.assertTrue(conn.execute("SELECT 1 FROM portal_production WHERE kind='audit' AND payload LIKE '%import_failed%'").fetchone())
        retry=self.apply(payload,preview);self.assertEqual(retry['status'],'applied')
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):conn.execute("UPDATE portal_excel_imports SET status='failed'")

    def test_company_b_apply_cannot_write_company_a(self):
        payload=self.payload({'Клиенты':[dict(client_ref='new',name='Only B',active=1)]})
        a_before=self.database_hashes()[portal.DB_PATH]
        result=self.apply(payload,token=self.other_admin)
        self.assertEqual(result['company_id'],self.other)
        self.assertEqual(self.database_hashes()[portal.DB_PATH],a_before)
        self.assertNotIn('Only B',[c['name'] for c in self.get('catalog')['data']['clients']])

    def test_future_tariff_append_preserves_catalog_values_work_and_closed_snapshots(self):
        work=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.worker)['data']
        with portal.db() as conn:
            r=Repository(conn,1);period=r.insert('payroll_periods',dict(status='closed',period_start='2020-01-01',period_end='2020-01-15',snapshot=dict(total_salary=12345,employees=[],details=[])))
            raw_period=conn.execute("SELECT payload FROM portal_production WHERE kind='payroll_periods' AND id=?",(period['id'],)).fetchone()[0]
            raw_work=conn.execute("SELECT payload FROM portal_production WHERE kind='works' AND id=?",(work['id'],)).fetchone()[0]
            old_rates=tuple(conn.execute('SELECT employee_rate,client_rate FROM portal_client_operations WHERE id=1').fetchone())
        future=(datetime.utcnow()+timedelta(days=4)).isoformat()
        data={'Клиенты':[dict(client_ref='c',client_id=1,name='Client')],
              'Операции_Тарифы':[dict(client_ref='c',client_id=1,operation_id=1,name='Packing',employee_rate='7.77',client_rate='9.99',active=1,effective_from=future)]}
        self.assertEqual(self.apply(self.payload(data))['status'],'applied')
        with portal.db() as conn:
            self.assertEqual(tuple(conn.execute('SELECT employee_rate,client_rate FROM portal_client_operations WHERE id=1').fetchone()),old_rates)
            self.assertEqual(conn.execute("SELECT payload FROM portal_production WHERE kind='payroll_periods' AND id=?",(period['id'],)).fetchone()[0],raw_period)
            self.assertEqual(conn.execute("SELECT payload FROM portal_production WHERE kind='works' AND id=?",(work['id'],)).fetchone()[0],raw_work)
            tariff=next(t for t in Repository(conn,1).list('tariffs') if t['employee_rate']==777)
            self.assertEqual(tariff['client_rate'],999)
