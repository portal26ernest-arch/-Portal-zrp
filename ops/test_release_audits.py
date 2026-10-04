from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]

def load(name, rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

legacy=load("legacy_audit","ops/legacy_runtime_audit.py")
money=load("money_inventory","ops/money_field_inventory.py")

class ReleaseAuditToolsTest(unittest.TestCase):
    def test_runtime_classification(self):
        self.assertEqual(
            legacy.classify("android_src/app/src/main/assets/app.js","const x=user.telegram_id;"),
            "runtime_direct_telegram_id",
        )
        self.assertEqual(
            legacy.classify("server/production_service.py","return user.get('employee_id',user.get('telegram_id'))"),
            "runtime_bridge",
        )
        self.assertEqual(
            legacy.classify("server/employee_identity.py","SELECT * FROM work_log WHERE telegram_id=?"),
            "runtime_bridge",
        )
        self.assertEqual(
            legacy.classify("server/migration_import.py","SELECT telegram_id FROM employees"),
            "runtime_bridge",
        )
        self.assertEqual(
            legacy.classify("server/portal_app_server.py","if 'telegram_id' in body:"),
            "runtime_bridge",
        )
        self.assertEqual(
            legacy.classify("android_src/tests/legacy-boundary.test.cjs","const x='BOT_TOKEN';"),
            "schema_test_or_legacy",
        )
        self.assertEqual(
            legacy.classify("server/production_service.py","url='https://api.telegram.org'"),
            "forbidden_external_runtime",
        )

    def test_runtime_scan_has_no_external_telegram_termux(self):
        data=legacy.scan(ROOT)
        self.assertEqual(data["counts"].get("forbidden_external_runtime",0),0)
        self.assertEqual(data["counts"].get("runtime_direct_telegram_id",0),0)
        self.assertGreater(data["counts"].get("runtime_bridge",0),0)

    def test_money_inventory_finds_legacy_and_minor_units(self):
        data=money.scan(ROOT)
        self.assertGreater(data["legacy_float_like_count"],0)
        self.assertGreater(len(data["cent_source_hits"]),0)

    def test_reports_are_text(self):
        self.assertIn("Release interpretation",legacy.report(legacy.scan(ROOT)))
        self.assertIn("Migration policy",money.report(money.scan(ROOT)))

if __name__=="__main__":
    unittest.main()
