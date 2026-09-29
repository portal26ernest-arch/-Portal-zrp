"""A4 PDF output smoke tests; ReportLab is pinned in server/requirements-test.txt."""
import importlib.util
import unittest

@unittest.skipUnless(importlib.util.find_spec('reportlab'), 'ReportLab runtime dependency is not installed')
class PdfDocumentsTest(unittest.TestCase):
    def test_invoice_and_short_payroll_slip_are_valid_a4_pdfs(self):
        from pdf_documents import invoice_pdf, payroll_slip_pdf
        company={'name':'Исполнитель','legal_name':'ООО Исполнитель','inn':'123'}
        client={'name':'Клиент','legal_name':'АО Клиент','inn':'456'}
        invoice={'created_at':'2026-09-29','lines':[{'operation_name':'Упаковка','quantity':2,
            'client_rate':1250,'amount':2500}],'amount':2500}
        statement=invoice_pdf(company,client,invoice,{})
        slip=payroll_slip_pdf(company,{'period_start':'2026-09-01','period_end':'2026-09-30'},
            {'display_name':'Сотрудник'}, {'balance':5500}, '2026-10-01')
        for payload in (statement,slip):
            self.assertTrue(payload.startswith(b'%PDF-'))
            self.assertIn(b'%%EOF',payload[-2048:])
            self.assertIn(b'/MediaBox',payload)
        self.assertLess(len(slip),len(statement)+10000)

if __name__=='__main__': unittest.main()
