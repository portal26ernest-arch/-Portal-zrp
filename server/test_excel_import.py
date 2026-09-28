"""Synthetic staged import: preview writes nothing; explicit apply is tested below."""
import base64
import hashlib
import io
import json
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
