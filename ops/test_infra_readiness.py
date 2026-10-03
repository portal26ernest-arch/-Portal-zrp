from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
import sys


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


backup = load("portal_backup", "ops/postgres_backup.py")
restore = load("portal_restore", "ops/postgres_restore_rehearsal.py")


class InfraReadinessTest(unittest.TestCase):
    def test_sha256_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x"
            p.write_bytes(b"portal")
            self.assertEqual(
                backup.sha256_file(p),
                hashlib.sha256(b"portal").hexdigest(),
            )

    def test_retention_only_prunes_old_portal_backup_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = root / "portal-pg-old.dump"
            keep = root / "portal-pg-current.dump"
            unrelated = root / "other-old.dump"
            old.write_bytes(b"old")
            keep.write_bytes(b"keep")
            unrelated.write_bytes(b"other")

            ancient = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).timestamp()
            import os
            os.utime(old, (ancient, ancient))
            os.utime(unrelated, (ancient, ancient))

            removed = backup.prune_old(root, "portal-pg-", 14, {keep})
            self.assertEqual(removed, ["portal-pg-old.dump"])
            self.assertFalse(old.exists())
            self.assertTrue(keep.exists())
            self.assertTrue(unrelated.exists())
            with self.assertRaises(ValueError):
                backup.prune_old(root, "../", 14, {keep})

    def test_restore_database_guard(self):
        good = restore.safe_db_name("portal_test_restore_abc123")
        self.assertEqual(good, "portal_test_restore_abc123")
        for bad in ("portal", "production", "portal_test_restore_x;drop", "portal_test_restore_X"):
            with self.assertRaises(ValueError):
                restore.safe_db_name(bad)

    def test_restore_validation_output_is_not_written_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dump = root / "source.dump"; sql = root / "check.sql"
            dump.write_bytes(b"dump"); sql.write_text("SELECT 'private payload';", encoding="utf-8")
            argv = ["restore", "--dump", str(dump), "--validation-sql", str(sql)]
            output = io.StringIO()
            def fake_run(args, *, capture=False):
                return __import__("subprocess").CompletedProcess(args, 0, "private payload" if capture else "", "")
            with patch.object(sys, "argv", argv), patch.object(restore, "run", side_effect=fake_run), contextlib.redirect_stdout(output):
                self.assertEqual(restore.main(), 0)
            self.assertNotIn("private payload", output.getvalue())
            self.assertNotIn("validation_output_tail", output.getvalue())

    def test_nginx_template_keeps_api_loopback_and_https(self):
        text = (ROOT / "deploy/nginx/portal.conf.template").read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://127.0.0.1:__PORTAL_LOOPBACK_PORT__;", text)
        self.assertIn("return 301 https://$host$request_uri;", text)
        self.assertIn("Strict-Transport-Security", text)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", text)
        self.assertNotIn("proxy_pass http://0.0.0.0:", text)
        self.assertNotIn("proxy_pass http://127.0.0.1:8770;", text)

    def test_systemd_backup_is_hardened_and_no_inline_password(self):
        text = (ROOT / "deploy/systemd/portal-backup.service").read_text(encoding="utf-8")
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("EnvironmentFile=/etc/portal/backup.env", text)
        self.assertNotIn("PGPASSWORD=", text)
        self.assertNotIn("password=", text.lower())

    def test_central_backup_covers_split_production_and_preserves_manual_checkpoints(self):
        text = (ROOT / "ops/portal_central_backup.sh").read_text(encoding="utf-8")
        self.assertIn("backup_database portal_prod_control", text)
        self.assertIn("portal_prod_company_[0-9]+", text)
        self.assertIn("grep -qx portal_prod_company_1", text)
        self.assertIn("pg_restore --list", text)
        self.assertIn('postgresql/daily', text)
        self.assertIn('storage/daily', text)
        self.assertIn('RETENTION_DAYS=14', text)
        self.assertNotIn('PGPASSWORD=', text)
        self.assertNotIn('password=', text.lower())

    def test_reminder_systemd_example_is_hardened_and_not_installed_by_default(self):
        service_path = ROOT / "ops/systemd/portal-reminder-scheduler.service.example"
        timer_path = ROOT / "ops/systemd/portal-reminder-scheduler.timer.example"
        self.assertTrue(service_path.is_file())
        self.assertTrue(timer_path.is_file())
        service = service_path.read_text(encoding="utf-8")
        timer = timer_path.read_text(encoding="utf-8")
        self.assertIn("ExecStart=/opt/portal/venv/bin/python /opt/portal/current/server/reminder_operator.py", service)
        self.assertIn("EnvironmentFile=/etc/portal/portal.env", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", service)
        self.assertNotIn("PGPASSWORD=", service)
        self.assertIn("OnCalendar=hourly", timer)
        self.assertIn("Unit=portal-reminder-scheduler.service", timer)
        self.assertTrue(service_path.name.endswith(".example"))
        self.assertTrue(timer_path.name.endswith(".example"))

    def test_source_mirror_sync_timer_is_hardened_and_tracks_main(self):
        service_path = ROOT / "ops/systemd/portal-source-sync.service"
        timer_path = ROOT / "ops/systemd/portal-source-sync.timer"
        self.assertTrue(service_path.is_file())
        self.assertTrue(timer_path.is_file())
        service = service_path.read_text(encoding="utf-8")
        timer = timer_path.read_text(encoding="utf-8")
        self.assertIn("PORTAL_SOURCE_BRANCH=main", service)
        self.assertIn("ExecStart=/usr/bin/bash /srv/portal-source/repo/ops/sync_vps_source_mirror.sh", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ReadWritePaths=/srv/portal-source", service)
        self.assertNotIn("password=", service.lower())
        self.assertNotIn("token=", service.lower())
        self.assertIn("OnUnitActiveSec=2min", timer)
        self.assertIn("Unit=portal-source-sync.service", timer)

    def test_api_service_is_loopback_hardened_and_fail_closed(self):
        service = (ROOT / "deploy/systemd/portal-api.service").read_text(encoding="utf-8")
        env = (ROOT / "deploy/systemd/portal.env.example").read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=/etc/portal/portal.env", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ReadWritePaths=/var/lib/portal/documents", service)
        self.assertIn("PORTAL_APP_HOST=127.0.0.1", env)
        self.assertIn("PORTAL_APP_PORT=8765", env)
        self.assertIn("PORTAL_ENABLE_POSTGRES_PRODUCTION=false", env)
        self.assertEqual(env.count("PORTAL_DATABASE_URL="), 1)
        self.assertEqual(env.count("PORTAL_CONTROL_DATABASE_URL="), 1)

    def test_example_env_has_no_secret_value(self):
        text = (ROOT / "ops/backup.env.example").read_text(encoding="utf-8")
        self.assertNotIn("PGPASSWORD=", text)
        self.assertIn("PGPASSFILE=/etc/portal/.pgpass", text)


if __name__ == "__main__":
    unittest.main()
