"""Synthetic HTTP document permissions, retries, archive and byte-store tests."""
import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from document_domain import LocalFileStorage, Documents, validate_upload, MAX_DOCUMENT_BYTES
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

    def upload(self,token=None,**values):
        body=dict(action='upload',document_type='report_pdf',original_filename='Отчёт.pdf',mime_type='application/pdf',
                  file_b64=base64.b64encode(PDF).decode(),title='Отчёт',category='reports',document_date='2026-09-28')
        body.update(values)
        return self.post('documents',body,token)['data']

    def test_upload_storage_checksum_metadata_and_duplicate_request(self):
        a=self.upload(request_id='doc-1');b=self.upload(request_id='doc-1')
        self.assertEqual(a['id'],b['id']);self.assertNotIn('file_b64',a);self.assertNotIn('storage_key',a)
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
        for values in ({'original_filename':'../x.pdf'},{'original_filename':'C:x.pdf'},{'mime_type':'text/plain'},
                       {'document_type':'invoice_xlsx'},{'file_b64':'bad!'},{'file_b64':''},{'employee_id':999999}):
            body=dict(action='upload',document_type='report_pdf',original_filename='x.pdf',mime_type='application/pdf',file_b64=base64.b64encode(PDF).decode())
            body.update(values);self.post('documents',body,status=400)
        with self.assertRaises(ValueError):validate_upload('x.pdf','application/pdf',b'x'*(MAX_DOCUMENT_BYTES+1),'report_pdf')
        self.assertEqual(self.get('documents')['data'],[])

class BlobStorageTest(unittest.TestCase):
    def test_content_addressed_company_keys_atomic_retry_and_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            store=LocalFileStorage(root);a=store.put(PDF,1);b=store.put(PDF,2)
            self.assertNotEqual(a,b);self.assertEqual(store.put(PDF,1),a)
            self.assertEqual(store.get(a,1),PDF)
            for key,cid in (('../x',1),(a,2),('1/'+'x'*64,1)):
                with self.assertRaises(PermissionError):store.get(key,cid)
            self.assertFalse(list(Path(root).rglob('.tmp-*')))
