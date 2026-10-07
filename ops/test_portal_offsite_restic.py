from pathlib import Path
import hashlib, importlib.util, json, os, tempfile, unittest
from datetime import datetime, timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("offsite_restic",ROOT/"ops/portal_offsite_restic.py")
app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
class OffsiteResticTests(unittest.TestCase):
    def test_missing_credentials_fail_closed_without_command(self):
        with patch.dict(os.environ,{},clear=True), patch.object(app.subprocess,"run") as run:
            with self.assertRaises(SystemExit) as e: app.require_configuration()
            self.assertEqual(e.exception.code,app.EXIT_CONFIG); run.assert_not_called()
    def test_exact_central_source_and_required_inventory_are_enforced(self):
        self.assertEqual(str(app.SOURCE).replace("\\","/"),"/srv/portal/central/backups")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); app.SOURCE=root
            marker=root/app.MARKER
            stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            marker.write_text(json.dumps({"schema":1,"completed_at_utc":stamp,"files":[]}))
            marker.touch()
            with self.assertRaises(SystemExit) as e: app.verified_inventory(30)
            self.assertEqual(e.exception.code,app.EXIT_VERIFY)
    def test_stale_local_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); app.SOURCE=root
            marker=root/app.MARKER
            marker.write_text(json.dumps({"schema":1,"completed_at_utc":"20000101T000000Z","files":[]}))
            with self.assertRaises(SystemExit) as e: app.verified_inventory(30)
            self.assertEqual(e.exception.code,app.EXIT_STALE)
    def test_backup_commands_include_retention_and_check(self):
        env={"RESTIC_REPOSITORY":"s3:https://objects.invalid/bucket/repo","RESTIC_PASSWORD_FILE":"pw","AWS_ACCESS_KEY_ID":"x","AWS_SECRET_ACCESS_KEY":"y","AWS_DEFAULT_REGION":"us-east-1"}
        with patch.dict(os.environ,env,clear=True), patch.object(app.Path,"is_file",return_value=True), patch.object(app.Path,"stat") as st, patch.object(app.os,"access",return_value=True), patch.object(app,"staged_payload",return_value=(type("TD",(),{"cleanup":lambda self:None})(),Path("/tmp/stage"))), patch.object(app,"run") as run:
            st.return_value.st_size=1
            app.backup(type("Args",(),{"max_age_hours":30})())
            commands=[c.args[0] for c in run.call_args_list]
            self.assertTrue(any("--keep-daily" in c and "--prune" in c for c in commands))
            self.assertTrue(any(len(c)>1 and c[1]=="check" for c in commands))
    def test_restore_has_no_production_destination(self):
        src=(ROOT/"ops/portal_offsite_restic.py").read_text()
        self.assertIn('TemporaryDirectory(prefix="portal-restore-test-")',src)
        self.assertIn('"--target",str(target)',src)
        self.assertNotIn("pg_restore --clean",src)
        self.assertNotIn("/srv/portal/central/storage",src)
    def test_examples_and_units_have_no_live_secrets(self):
        files=[ROOT/"ops/offsite-backup.env.example",ROOT/"deploy/systemd/portal-offsite-backup.service",ROOT/"deploy/systemd/portal-offsite-restore-test.service"]
        for p in files:
            text=p.read_text().lower()
            self.assertNotRegex(text,r"(aws_access_key_id|aws_secret_access_key)=\S+")
            self.assertIn("nonewprivileges=yes",text) if p.suffix==".service" else None
        self.assertIn("RESTIC_PASSWORD_FILE",files[0].read_text())
if __name__=="__main__": unittest.main()
