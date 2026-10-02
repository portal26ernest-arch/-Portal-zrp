import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("r",ROOT/"ops/rollback_rehearsal.py");r=importlib.util.module_from_spec(s);s.loader.exec_module(r)

class RollbackRehearsalTest(unittest.TestCase):
    def fixture(self,root,encrypted=False):
        name="portal-pg-test.dump.age" if encrypted else "portal-pg-test.dump"
        backup=root/name;backup.write_bytes(b"verified-backup");digest=hashlib.sha256(backup.read_bytes()).hexdigest()
        manifest=root/"portal-pg-test.json";manifest.write_text(json.dumps({"file":name,"sha256":digest,"verified_pg_restore_list":True,"encrypted":encrypted}),encoding="utf-8")
        (root/"portal-pg-test.sha256").write_text(digest+"  "+name+"\n",encoding="utf-8")
        evidence=root/"evidence.json";evidence.write_text(json.dumps({"backup_restore_rehearsed":True,"restore_cleanup_verified":True,"migration_dry_run":True,"reconciliation":True,"tenant_isolation":True,"financial_invariants":True,"production_untouched":True,"backup_decryption_rehearsed":True}),encoding="utf-8")
        return manifest,evidence
    def test_ready_read_only_rehearsal(self):
        with tempfile.TemporaryDirectory() as td:
            m,e=self.fixture(Path(td));out=r.build(m,e,"https://old.example","https://new.example")
            self.assertTrue(out["ready"]);self.assertFalse(out["production_mutation_performed"])
    def test_failed_flag_is_no_go(self):
        with tempfile.TemporaryDirectory() as td:
            m,e=self.fixture(Path(td));data=json.loads(e.read_text());data["financial_invariants"]=False;e.write_text(json.dumps(data))
            out=r.build(m,e);self.assertFalse(out["ready"]);self.assertIn("missing_or_failed:financial_invariants",out["blockers"])
    def test_encrypted_requires_decryption_rehearsal(self):
        with tempfile.TemporaryDirectory() as td:
            m,e=self.fixture(Path(td),True);data=json.loads(e.read_text());data["backup_decryption_rehearsed"]=False;e.write_text(json.dumps(data))
            out=r.build(m,e);self.assertFalse(out["ready"]);self.assertIn("missing_or_failed:backup_decryption_rehearsed",out["blockers"])
    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            m,e=self.fixture(Path(td));data=json.loads(m.read_text());data["sha256"]="0"*64;m.write_text(json.dumps(data))
            with self.assertRaises(r.RollbackEvidenceError):r.build(m,e)
    def test_endpoint_validation(self):
        for bad in ("http://portal.example","https://user:pass@portal.example","https://portal.example?token=x","https://portal.example:8443"):
            with self.assertRaises(r.RollbackEvidenceError):r.validate_https(bad)
        self.assertEqual(r.validate_https("https://portal.example/"),"https://portal.example")
    def test_same_endpoint_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            m,e=self.fixture(Path(td))
            with self.assertRaises(r.RollbackEvidenceError):r.build(m,e,"https://portal.example","https://portal.example")

if __name__=="__main__":unittest.main()
