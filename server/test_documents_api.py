"""Synthetic HTTP document permissions, retries, archive and byte-store tests."""
import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
import sys
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from document_domain import LocalFileStorage, Documents, validate_upload, MAX_DOCUMENT_BYTES
from production_repository import Repository
import test_production as fixtures

portal=fixtures.portal
PDF=b'%PDF-1.4\nsynthetic document\n%%EOF\n'

class DocumentAPITest(unittest.TestCase):
    request=fixtures.ProductionTest.request
    tearDown=fixtures.ProductionTest.tearDown
    setUp=fixtures.ProductionTest.setUp
    role_token=fixtures.ProductionTest.role_token
    post=fixtures.ProductionTest.post
    get=fixtures.ProductionTest.get
    work=fixtures.ProductionTest.work

    def upload(self,token=None,**values):
        body=dict(action='upload',document_type='report_pdf',original_filename='Отчёт.pdf',mime_type='application/pdf',
                  file_b64=base64.b64encode(PDF).decode(),title='Отчёт',category='reports',document_date='2026-09-28')
        body.update(values)
        return self.post('documents',body,token)['data']

    def test_upload_storage_checksum_metadata_and_duplicate_request(self):
        a=self.upload(request_id='doc-1');b=self.upload(request_id='doc-1')
        self.assertEqual(a['id'],b['id']);self.assertNotIn('file_b64',a);self.assertNotIn('storage_key',a)
        duplicate=self.upload(request_id='doc-duplicate')
        self.assertEqual(duplicate['id'],a['id'])
        self.assertEqual(a['checksum_sha256'],hashlib.sha256(PDF).hexdigest())
        self.assertEqual(len(self.get('documents')['data']),1)
        download=self.get('document-file?id='+a['id'])['data']
        self.assertEqual(base64.b64decode(download['file_b64']),PDF)
        with portal.db() as conn:
            raw=conn.execute('SELECT metadata,storage_key FROM portal_documents').fetchone()
            self.assertNotIn('file_b64',raw[0]);self.assertTrue(raw[1].startswith('1/'))
        self.post('documents',dict(action='upload',document_type='report_pdf',original_filename='Other.pdf',mime_type='application/pdf',file_b64=base64.b64encode(PDF).decode(),request_id='doc-1'),status=400)

    def test_cross_company_read_download_archive_and_reference(self):
        other=self.upload(self.other_admin)
        self.assertEqual(self.get('documents')['data'],[])
        for action in ('document-file','document-metadata'):
            self.get(action+'?id='+other['id'],status=400)
        self.post('documents',dict(action='archive',id=other['id']),status=400)
        self.post('documents',dict(action='upload',document_type='report_pdf',original_filename='x.pdf',mime_type='application/pdf',file_b64=base64.b64encode(PDF).decode(),client_id=900),status=403)
        self.post('documents',dict(company_id=self.other,action='archive',id=other['id']),status=403)

    def test_role_matrix_manager_scope_payroll_and_owner(self):
        doc=self.upload(client_id=1)
        manager=self.role_token('manager');director=self.role_token('director')
        self.assertEqual(self.get('documents',manager)['data'],[])
        with portal.db() as conn:
            conn.execute('INSERT INTO manager_client_assignments(telegram_id,client_id,active,company_id) VALUES(101,1,1,1)')
        self.assertEqual(self.get('documents',manager)['data'][0]['id'],doc['id'])
        self.upload(client_id=None)
        self.assertEqual(len(self.get('documents',manager)['data']),1)
        self.post('documents',dict(action='archive',id=doc['id']),manager,status=403)
        self.assertEqual(len(self.get('documents',director)['data']),2)
        self.get('documents',self.worker,status=403)
        self.request('/api/v3/documents',self.owner,status=403)
        owner=self.request('/api/v3/documents',self.owner,extra_headers={'X-Portal-Company':'1'})
        self.assertEqual(len(owner['data']),2)

    def test_archive_keeps_metadata_blocks_download_and_is_idempotent(self):
        doc=self.upload()
        self.post('documents',dict(action='archive',id=doc['id']))
        self.post('documents',dict(action='archive',id=doc['id']))
        self.assertEqual(self.get('documents')['data'],[])
        self.assertEqual(self.get('documents?status=archived')['data']['total'],1)
        self.get('document-file?id='+doc['id'],status=400)
        self.assertEqual(self.get('document-metadata?id='+doc['id'])['data']['status'],'archived')
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_documents').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM portal_production WHERE kind='audit' AND payload LIKE '%document_archived%'").fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM portal_documents')

    def test_missing_file_and_corrupt_blob_keep_metadata(self):
        doc=self.upload()
        with portal.db() as conn:key=conn.execute('SELECT storage_key FROM portal_documents').fetchone()[0]
        root=Path(portal.DB_PATH).parent/'.portal-documents'
        (root/key).write_bytes(b'corrupt')
        self.get('document-file?id='+doc['id'],status=400)
        (root/key).unlink()
        self.get('document-file?id='+doc['id'],status=400)
        self.assertEqual(self.get('document-metadata?id='+doc['id'])['data']['id'],doc['id'])

    def test_pagination_search_filters_and_safe_inputs(self):
        self.upload(title='Первый отчёт',client_id=1)
        self.upload(title='Другой документ',category='other',document_date='2026-09-29')
        result=self.get('documents?page=2&limit=1')['data'];self.assertEqual((result['total'],len(result['items'])),(2,1))
        for query in ('q=%D0%9F%D0%B5%D1%80%D0%B2%D1%8B%D0%B9','category=reports','client_id=1','date_from=2026-09-28&date_to=2026-09-28'):
            self.assertEqual(self.get('documents?'+query)['data']['total'],1)
        self.assertEqual(self.get("documents?q=%27%20OR%201%3D1")["data"]["total"],0)
        self.get('documents?limit=201',status=400)
        self.get('documents?date_from=bad',status=400)

    def test_invalid_filename_mime_size_type_and_employee_reference(self):
        for values in ({'original_filename':'../x.pdf'},{'original_filename':'C:x.pdf'},{'original_filename':'x.pdf '},{'original_filename':' x.pdf'},{'mime_type':'text/plain'},
                       {'document_type':'invoice_xlsx'},{'file_b64':'bad!'},{'file_b64':''},{'employee_id':999999}):
            body=dict(action='upload',document_type='report_pdf',original_filename='x.pdf',mime_type='application/pdf',file_b64=base64.b64encode(PDF).decode())
            body.update(values);self.post('documents',body,status=400)
        with self.assertRaises(ValueError):validate_upload('x.pdf','application/pdf',b'x'*(MAX_DOCUMENT_BYTES+1),'report_pdf')
        self.assertEqual(self.get('documents')['data'],[])

    def test_invoice_pdf_generation_permissions_tenant_scope_and_financial_immutability(self):
        work=self.work()
        invoice=self.post('invoices',dict(work_ids=[work['id']]))['data']
        before=(self.get('works')['data'],self.get('invoices')['data'])
        renderer=SimpleNamespace(invoice_pdf=lambda *args: PDF)
        import documents_api
        errors=[];original_route=documents_api.route
        def traced(*args):
            try:return original_route(*args)
            except Exception as error:errors.append(error);raise
        with patch.dict(sys.modules,{'pdf_documents':renderer}),patch('documents_api.route',side_effect=traced):
            try:doc=self.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']))['data']
            except AssertionError:self.fail('PDF route failed: '+repr(errors))
            self.assertEqual(doc['document_type'],'invoice_pdf')
            self.assertEqual(doc['client_id'],invoice['client_id'])
            self.assertEqual(base64.b64decode(self.get('document-file?id='+doc['id'])['data']['file_b64']),PDF)
            self.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']),self.worker,status=403)
            self.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']),self.other_admin,status=400)
            self.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id='unknown',employee_id=1),self.worker,status=403)
        after=(self.get('works')['data'],self.get('invoices')['data'])
        self.assertEqual(after,before)
        with portal.db() as conn:
            row=conn.execute('SELECT status,document_type FROM portal_documents WHERE id=?',(doc['id'],)).fetchone()
            self.assertEqual(tuple(row),('ready','invoice_pdf'))

    def test_payroll_slip_uses_closed_snapshot_permissions_scope_and_immutable_facts(self):
        work=self.work();today=datetime.utcnow().date()
        if today.day>15:start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
        else:
            previous=today.replace(day=1)-timedelta(days=1)
            start=previous.replace(day=16).isoformat();end=previous.isoformat()
        with portal.db() as conn:
            repo=Repository(conn,1)
            source=dict(work,id=str(uuid.uuid4()),completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
            repo.insert('works',{k:v for k,v in source.items() if k not in {'id','company_id'}},source['id'])
            conn.commit()
        period=self.post('payroll-periods',dict(period_start=start,period_end=end))['data']
        employee=period['snapshot']['employees'][0]
        with portal.db() as conn:
            payroll_employee=Repository(conn,1).payroll_employee(employee['employee_id'],legacy=True)['employee_id']
            settlements_before=Repository(conn,1).payroll_settlements(period['id'],payroll_employee)
        renderer=SimpleNamespace(payroll_slip_pdf=lambda *args: PDF)
        with patch.dict(sys.modules,{'pdf_documents':renderer}):
            doc=self.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=payroll_employee))['data']
            self.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=payroll_employee),self.worker,status=403)
            self.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=payroll_employee),self.other_admin,status=400)
        self.assertEqual(doc['document_type'],'payroll_slip_pdf')
        self.assertEqual(doc['employee_id'],payroll_employee)
        self.assertEqual(doc['payroll_period_id'],period['id'])
        self.assertEqual(base64.b64decode(self.get('document-file?id='+doc['id'])['data']['file_b64']),PDF)
        saved=next(p for p in self.get('payroll-periods')['data'] if p['id']==period['id'])
        self.assertEqual(saved['snapshot'],period['snapshot'])
        with portal.db() as conn:
            settlements_after=Repository(conn,1).payroll_settlements(period['id'],payroll_employee)
        self.assertEqual(settlements_after,settlements_before)

class BlobStorageTest(unittest.TestCase):
    def test_content_addressed_company_keys_atomic_retry_and_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            store=LocalFileStorage(root);a=store.put(PDF,1);b=store.put(PDF,2)
            self.assertNotEqual(a,b);self.assertEqual(store.put(PDF,1),a)
            self.assertEqual(store.get(a,1),PDF)
            for key,cid in (('../x',1),(a,2),('1/'+'x'*64,1)):
                with self.assertRaises(PermissionError):store.get(key,cid)
            self.assertFalse(list(Path(root).rglob('.tmp-*')))
