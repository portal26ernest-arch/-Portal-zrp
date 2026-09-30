import importlib.util, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('identity_audit',ROOT/'ops/employee_identity_migration_audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class IdentityMigrationAuditTest(unittest.TestCase):
    def row(self,path,line,kind='runtime_direct_telegram_id'):
        return {'path':path,'line':1,'kind':kind,'text':line}

    def test_active_sql_dependency_is_p0(self):
        r=self.row('server/portal_app_server.py','SELECT * FROM work_log WHERE telegram_id=?')
        self.assertEqual(audit.classify(r),'P0_runtime_identity_dependency')

    def test_explicit_bridge_is_p1(self):
        r=self.row('server/production_service.py',"return user.get('employee_id',user.get('telegram_id'))",'runtime_bridge')
        self.assertEqual(audit.classify(r),'P1_explicit_compatibility_bridge')

    def test_import_boundary_is_p1(self):
        r=self.row('server/excel_import.py','SELECT telegram_id FROM employees')
        self.assertEqual(audit.classify(r),'P1_import_export_boundary')
    def test_fixture_is_p2(self):
        r=self.row('server/web_pg_part10_fixture_host.py','SELECT telegram_id FROM app_users')
        self.assertEqual(audit.classify(r),'P2_fixture_support')

    def test_canonical_adapter_is_the_only_allowed_runtime_bridge(self):
        r=self.row('server/employee_identity.py','SELECT * FROM work_log WHERE telegram_id=?')
        self.assertEqual(audit.classify(r),'P1_explicit_compatibility_bridge')

    def test_direct_runtime_outside_adapter_remains_p0(self):
        r=self.row('server/portal_app_server.py','SELECT * FROM work_log WHERE telegram_id=?')
        self.assertEqual(audit.classify(r),'P0_runtime_identity_dependency')

    def test_actual_scan_has_no_forbidden_external_runtime(self):
        data=audit.build(ROOT)
        self.assertEqual(data['counts'].get('P0_forbidden_external_runtime',0),0)
        self.assertEqual(data['counts'].get('P0_runtime_identity_dependency',0),0)
        self.assertGreater(data['counts'].get('P1_explicit_compatibility_bridge',0),0)

    def test_report_is_actionable(self):
        text=audit.report(audit.build(ROOT))
        self.assertIn('P0 active runtime identity dependencies',text)
        self.assertIn('Files requiring action',text)
        self.assertIn('server/portal_app_server.py',text)

if __name__=='__main__':unittest.main()
