"""Static contract complements the opt-in real PostgreSQL/HTTP fixture."""
import re
import unittest
from pathlib import Path

SQL=(Path(__file__).parent/'migrations'/'postgresql_stage8_documents_excel.sql').read_text(encoding='utf-8')

class PostgreSQLDocumentsSchemaContract(unittest.TestCase):
    def test_additive_transactional_repeatable_migration_and_new_company_marker(self):
        statements=re.sub(r'--[^\n]*','',SQL).strip()
        self.assertTrue(statements.startswith('BEGIN;'));self.assertTrue(statements.endswith('COMMIT;'))
        for table in ('portal_documents','portal_excel_imports'):
            self.assertIn('CREATE TABLE IF NOT EXISTS '+table,SQL)
        self.assertIn('(cid,7,CURRENT_TIMESTAMP::text)',SQL)
        self.assertIn('ON CONFLICT(company_id,version) DO NOTHING',SQL)
        self.assertNotRegex(statements,r'(?i)\b(?:DROP\s+TABLE|TRUNCATE|DELETE\s+FROM|UPDATE\s+(?:work_log|portal_production|portal_client_operations|payroll_\w+))\b')

    def test_protected_forced_rls_and_restricted_runtime_grants(self):
        for table in ('portal_documents','portal_excel_imports'):
            for command in ('ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY','ALTER COLUMN company_id SET DEFAULT portal_current_company()'):
                self.assertIn('ALTER TABLE '+table+' '+command,SQL)
        self.assertIn('USING (company_id=portal_current_company()) WITH CHECK (company_id=portal_current_company())',SQL)
        self.assertIn('NOT rolsuper AND NOT rolbypassrls',SQL)
        self.assertIn('GRANT SELECT,INSERT,UPDATE ON portal_documents,portal_excel_imports',SQL)
        self.assertNotRegex(SQL,r'GRANT[^;]*DELETE')
        self.assertIn('REVOKE ALL ON portal_documents,portal_excel_imports FROM PUBLIC',SQL)

    def test_scoped_references_jsonb_and_idempotent_indexes(self):
        for key,target in (('client_id','portal_clients(company_id,id)'),('employee_id','payroll_employee_identities(company_id,employee_id)'),('previous_id','portal_documents(company_id,id)'),('result_document_id','portal_documents(company_id,id)')):
            self.assertIn('FOREIGN KEY(company_id,'+key+') REFERENCES '+target,SQL)
        for kind in ('invoice','payroll_period'):
            self.assertIn('FOREIGN KEY(company_id,'+kind+'_kind,'+kind+'_id) REFERENCES portal_production(company_id,kind,id)',SQL)
        for field,shape in (('metadata','object'),('preview_summary','object'),('result_counts','object'),('error_report','array')):
            self.assertIn(field+" JSONB NOT NULL CHECK(jsonb_typeof("+field+")='"+shape+"')",SQL)
        self.assertIn('UNIQUE(company_id,checksum)',SQL);self.assertIn('UNIQUE(company_id,request_id)',SQL)
        for name in ('documents_filter','documents_refs','documents_fingerprint','imports_actor'):
            self.assertIn('CREATE INDEX IF NOT EXISTS '+name,SQL)

    def test_archive_only_and_terminal_import_immutability(self):
        self.assertIn("OLD.status='ready' AND NEW.status='archived'",SQL)
        self.assertIn("to_jsonb(NEW)-'status'=to_jsonb(OLD)-'status'",SQL)
        self.assertIn("OLD.status='failed' AND NEW.status IN ('failed','applied')",SQL)
        self.assertIn('NEW.company_id=OLD.company_id AND NEW.import_id=OLD.import_id',SQL)
        self.assertIn('NEW.checksum=OLD.checksum AND NEW.template_version=OLD.template_version',SQL)
        for table in ('portal_documents','portal_excel_imports'):
            self.assertIn('BEFORE UPDATE OR DELETE ON '+table,SQL)

if __name__=='__main__':unittest.main()
