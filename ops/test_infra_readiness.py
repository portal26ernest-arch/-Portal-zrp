from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


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

    def test_restore_database_guard(self):
        good = restore.safe_db_name("portal_test_restore_abc123")
        self.assertEqual(good, "portal_test_restore_abc123")
        for bad in ("portal", "production", "portal_test_restore_x;drop", "portal_test_restore_X"):
            with self.assertRaises(ValueError):
                restore.safe_db_name(bad)

    def test_nginx_template_keeps_api_loopback_and_https(self):
        text = (ROOT / "deploy/nginx/portal.conf.template").read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://127.0.0.1:8770;", text)
        self.assertIn("return 301 https://$host$request_uri;", text)
        self.assertIn("Strict-Transport-Security", text)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", text)
        self.assertNotIn("0.0.0.0:8770", text)

    def test_systemd_backup_is_hardened_and_no_inline_password(self):
        text = (ROOT / "deploy/systemd/portal-backup.service").read_text(encoding="utf-8")
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("EnvironmentFile=/etc/portal/backup.env", text)
        self.assertNotIn("PGPASSWORD=", text)
        self.assertNotIn("password=", text.lower())

    def test_example_env_has_no_secret_value(self):
        text = (ROOT / "ops/backup.env.example").read_text(encoding="utf-8")
        self.assertNotIn("PGPASSWORD=", text)
        self.assertIn("PGPASSFILE=/etc/portal/.pgpass", text)


if __name__ == "__main__":
    unittest.main()
