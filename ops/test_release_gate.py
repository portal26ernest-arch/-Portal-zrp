from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(name,rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

gate=load("release_gate","ops/release_gate.py")
dry=load("cutover_dry_run","ops/cutover_dry_run.py")

class ReleaseGateTest(unittest.TestCase):
    def staging(self):
        return {
            "git_sha":"a"*40,
            "worktree_clean":True,
            "ci_server":True,"ci_web":True,"ci_android_ui":True,"ci_android_build":True,
            "tenant_isolation":True,"rls_force":True,"secrets_scan":True,"financial_invariants":True,
            "backup_created":True,"backup_restore_rehearsed":True,"migration_dry_run":True,
            "reconciliation":True,"production_untouched":True,
            "release_payload_complete":True,"api_smoke":True,"web_smoke":True,"runtime_release_verified":True,
            "staging_apk_sha256":"b"*64,"staging_version_name":"3.5-dev-staging","staging_version_code":35,
        }

    def test_staging_go(self):
        errors,failures=gate.validate(self.staging(),"staging")
        self.assertEqual(errors,[]);self.assertEqual(failures,[])

    def test_staging_missing_or_failed_is_no_go(self):
        x=self.staging();x.pop("rls_force")
        errors,failures=gate.validate(x,"staging")
        self.assertIn("missing:rls_force",errors)
        x=self.staging();x["financial_invariants"]=False
        errors,failures=gate.validate(x,"staging")
        self.assertIn("financial_invariants",failures)
        x=self.staging();x["worktree_clean"]=False
        errors,failures=gate.validate(x,"staging")
        self.assertIn("worktree_clean",failures)

    def test_production_requires_non_dev_https_signing_and_owner(self):
        x=self.staging()
        x.update({
            "production_https_url":"http://portal.example",
            "tls_valid":False,"production_signing":False,"offsite_backup_verified":False,
            "owner_authorized_cutover":False,"write_freeze_confirmed":False,"independent_verifier":False,
        })
        _,failures=gate.validate(x,"production")
        for key in ("production_version_is_dev","production_https_url","owner_authorized_cutover","production_signing"):
            self.assertIn(key,failures)

    def test_dry_run_protects_repository_derived_fields(self):
        with patch.object(dry,"git",side_effect=lambda args:"deadbeef" if args[0]=="rev-parse" else ("branch" if args[0]=="branch" else "")):
            with patch.object(dry,"migration_checksums",return_value={"x.sql":"a"*64}):
                data=dry.collect({"git_sha":"evil","production_untouched":False,"ci_server":True})
        self.assertEqual(data["git_sha"],"deadbeef")
        self.assertTrue(data["production_untouched"])
        self.assertTrue(data["ci_server"])

    def test_migration_checksums_are_sha256(self):
        result=dry.migration_checksums()
        self.assertGreater(len(result),0)
        self.assertTrue(all(len(v)==64 for v in result.values()))

if __name__=="__main__":
    unittest.main()
