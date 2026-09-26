"""Static security contract for the Stage 4C compatibility schema."""
import re
import unittest
from pathlib import Path

SQL = (Path(__file__).parent / 'migrations' / 'postgresql_stage4c.sql').read_text(encoding='utf-8')
TABLES = (
    'backup_log','client_access','client_invites','client_invoice_items',
    'client_name_overrides','client_permissions','employee_access_requests',
    'employee_chat_messages','employee_chat_settings','employee_invites',
    'expense_requests','managers','marketplace_news','payroll_closure_batches',
    'portal_client_requisites','portal_company_requisites',
    'portal_manager_service_rates','production_job_assignments','products',
    'scheduled_runs','system_settings','tariff_versions','user_roles',
)

class PostgreSQLStage4CSchemaContract(unittest.TestCase):
    def test_migration_is_transactional(self):
        statements = re.sub(r'--[^\n]*', '', SQL).strip()
        self.assertTrue(statements.startswith('BEGIN;'))
        self.assertTrue(statements.endswith('COMMIT;'))

    def test_all_stage4c_tables_are_forced_rls(self):
        for table in TABLES:
            self.assertIn("'" + table + "'", SQL)
        self.assertIn("ALTER TABLE %I ENABLE ROW LEVEL SECURITY", SQL)
        self.assertIn("ALTER TABLE %I FORCE ROW LEVEL SECURITY", SQL)

    def test_policies_use_protected_company_context(self):
        policy = re.search(r"CREATE POLICY portal_company.*?WITH CHECK.*?',\n\s*t", SQL, re.S)
        self.assertIsNotNone(policy)
        text = policy.group(0)
        self.assertIn('portal_current_company()', text)
        self.assertNotIn('current_setting', text)

    def test_legacy_columns_needed_by_phone_are_preserved(self):
        for fragment in (
            'work_log ADD COLUMN IF NOT EXISTS product_id',
            'work_log ADD COLUMN IF NOT EXISTS tariff_version_id',
            'portal_clients ADD COLUMN IF NOT EXISTS source',
            'production_jobs ADD COLUMN IF NOT EXISTS note',
        ):
            self.assertIn(fragment, SQL)

if __name__ == '__main__':
    unittest.main()
