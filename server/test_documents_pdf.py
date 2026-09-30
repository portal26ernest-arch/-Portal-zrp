"""A4 PDF output smoke tests; ReportLab is pinned in server/requirements-test.txt."""
import importlib.util
import base64
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('reportlab'), 'ReportLab runtime dependency is not installed')
class PdfDocumentsTest(unittest.TestCase):
    def test_real_invoice_and_closed_payroll_routes_render_and_register_test_records(self):
        # Exercise the production routes with records built by the existing isolated
        # server fixtures. No invoice requisites are supplied by this test.
        import test_documents_api as api_fixtures
        from production_repository import Repository
        from pdf_documents import _write as real_write
        api=api_fixtures.DocumentAPITest(methodName='test_invoice_pdf_generation_permissions_tenant_scope_and_financial_immutability')
        api.setUp()
        captured=[]
        def capture(title,rows):
            captured.append((title,list(rows)))
            return real_write(title,rows)
        try:
            work=api.work()
            invoice=api.post('invoices',dict(work_ids=[work['id']]))['data']
            invoice_before=(api.get('works')['data'],api.get('invoices')['data'])
            with patch('pdf_documents._write',side_effect=capture):
                invoice_doc=api.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']))['data']
                invoice_bytes=base64.b64decode(api.get('document-file?id='+invoice_doc['id'])['data']['file_b64'])
                self.assertTrue(invoice_bytes.startswith(b'%PDF-'))
                self.assertIn(b'%%EOF',invoice_bytes[-2048:])
                self.assertIn(b'/MediaBox',invoice_bytes)
                self.assertEqual(invoice_doc['document_type'],'invoice_pdf')
                api.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']))
                self.assertEqual((api.get('works')['data'],api.get('invoices')['data']),invoice_before)

                today=datetime.utcnow().date()
                if today.day>15:
                    start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
                else:
                    previous=today.replace(day=1)-timedelta(days=1)
                    start=previous.replace(day=16).isoformat();end=previous.isoformat()
                historical=dict(work,id='pdf-smoke-'+work['id'],completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
                with api_fixtures.portal.db() as conn:
                    Repository(conn,1).insert('works',{k:v for k,v in historical.items() if k not in {'id','company_id'}},historical['id'])
                    conn.commit()
                period=api.post('payroll-periods',dict(period_start=start,period_end=end))['data']
                employee_id=period['snapshot']['employees'][0]['employee_id']
                with api_fixtures.portal.db() as conn:
                    repo=Repository(conn,1)
                    settlements_before=repo.payroll_settlements(period['id'],employee_id)
                payroll_doc=api.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=employee_id))['data']
                payroll_bytes=base64.b64decode(api.get('document-file?id='+payroll_doc['id'])['data']['file_b64'])
                api.post('document-generate',dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=employee_id))
            self.assertTrue(payroll_bytes.startswith(b'%PDF-'))
            self.assertIn(b'%%EOF',payroll_bytes[-2048:])
            self.assertIn(b'/MediaBox',payroll_bytes)
            from reportlab.pdfbase import pdfmetrics
            self.assertIn(ord('\u0420'),pdfmetrics.getFont('PortalUnicode').face.charToGlyph)
            self.assertEqual(payroll_doc['document_type'],'payroll_slip_pdf')
            payroll_title,payroll_rows=captured[-1]
            labels=[label for label,_ in payroll_rows]
            self.assertLess(labels.index('\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0435\u0439'),labels.index('\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439 \u043f\u043e\u0434\u0440\u0430\u0437\u0434\u0435\u043b\u0435\u043d\u0438\u0435\u043c'))
            self.assertLess(labels.index('\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439 \u043f\u043e\u0434\u0440\u0430\u0437\u0434\u0435\u043b\u0435\u043d\u0438\u0435\u043c'),labels.index('\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a'))
            self.assertNotIn('\u041a\u043b\u0438\u0435\u043d\u0442',labels)
            self.assertFalse(any(label.startswith('\u041f\u043e\u0437\u0438\u0446\u0438\u044f ') for label in labels))
            self.assertNotIn('Packing',str(payroll_rows))
            with api_fixtures.portal.db() as conn:
                self.assertEqual(Repository(conn,1).payroll_settlements(period['id'],employee_id),settlements_before)
        finally:
            api.tearDown()

if __name__=='__main__': unittest.main()
