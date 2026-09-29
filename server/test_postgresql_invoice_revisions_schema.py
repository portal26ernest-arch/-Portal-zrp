"""Static contract for the opt-in PostgreSQL invoice lifecycle migration."""
import re
import unittest
from pathlib import Path

SQL=(Path(__file__).parent/'migrations'/'postgresql_stage9_invoice_revisions.sql').read_text(encoding='utf-8')

class PostgreSQLInvoiceRevisionSchemaContract(unittest.TestCase):
    def test_migration_is_additive_transactional_and_repeatable(self):
        statements=re.sub(r'--[^\n]*','',SQL).strip()
        self.assertTrue(statements.startswith('BEGIN;'))
        self.assertTrue(statements.endswith('COMMIT;'))
        self.assertIn('SELECT id,9,CURRENT_TIMESTAMP::text FROM companies',SQL)
        self.assertIn('ON CONFLICT(company_id,version) DO NOTHING',SQL)
        self.assertNotRegex(statements,r'(?i)\b(?:DROP\s+TABLE|TRUNCATE|DELETE\s+FROM)\b')
        self.assertNotRegex(statements,r'(?i)\bUPDATE\b')

    def test_runtime_and_postgresql_fixture_apply_readiness_marker(self):
        source=(Path(__file__).parent/'production_migrations.py').read_text(encoding='utf-8')
        self.assertIn('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,9,?)',source)
        self.assertIn("version=9",source)
        fixture=(Path(__file__).parent/'test_documents_postgresql.py').read_text(encoding='utf-8')
        self.assertIn("'postgresql_stage9_invoice_revisions.sql'",fixture)

if __name__=='__main__':unittest.main()
