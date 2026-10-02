from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("offsite",ROOT/"ops/offsite_backup.py")
offsite=importlib.util.module_from_spec(spec);spec.loader.exec_module(offsite)

class OffsiteBackupTest(unittest.TestCase):
    def bundle(self,root: Path):
        backup=root/"portal-pg-20260930.dump"
        backup.write_bytes(b"portal-backup")
        digest=hashlib.sha256(backup.read_bytes()).hexdigest()
        manifest=root/"portal-pg-20260930.json"
        manifest.write_text(json.dumps({"file":backup.name,"sha256":digest}),encoding="utf-8")
        (root/"portal-pg-20260930.sha256").write_text(digest+"  "+backup.name+"\n",encoding="utf-8")
        return manifest,digest

    def test_filesystem_export_verifies_all_files(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            manifest,digest=self.bundle(Path(a))
            result=offsite.filesystem_export(manifest,Path(b))
            self.assertTrue(result["verified"])
            self.assertEqual(result["backup_sha256"],digest)
            self.assertEqual(len(result["files"]),3)

    def test_manifest_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as a:
            manifest,_=self.bundle(Path(a))
            data=json.loads(manifest.read_text())
            data["sha256"]="0"*64
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                offsite.load_bundle(manifest)

    def test_secretish_targets_are_rejected(self):
        for target in ("s3://user:pass@example/bucket","remote:path?token=abc"," access "):
            with self.assertRaises(ValueError):
                offsite.validate_target(target)

    def test_rclone_commands_have_no_shell_and_use_immutable(self):
        with tempfile.TemporaryDirectory() as a:
            manifest,_=self.bundle(Path(a))
            calls=[]
            def fake(argv,check):
                calls.append(argv)
                class R:returncode=0
                return R()
            with patch.object(offsite.subprocess,"run",side_effect=fake):
                result=offsite.rclone_export(manifest,"vault:portal","rclone")
            self.assertTrue(result["verified"])
            self.assertEqual(len(calls),6)
            self.assertTrue(all(isinstance(c,list) for c in calls))
            self.assertIn("--immutable",calls[0])

if __name__=="__main__":
    unittest.main()
