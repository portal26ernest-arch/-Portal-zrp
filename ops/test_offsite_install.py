from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "ops" / "install_offsite_backup_ubuntu.sh").read_text(encoding="utf-8")
BACKUP_UNIT = (ROOT / "deploy" / "systemd" / "portal-offsite-backup.service").read_text(encoding="utf-8")
RESTORE_UNIT = (ROOT / "deploy" / "systemd" / "portal-offsite-restore-test.service").read_text(encoding="utf-8")

class OffsiteInstallTests(unittest.TestCase):
    def test_units_use_stable_installed_runtime(self):
        stable = "/usr/local/libexec/portal-offsite/current/portal_offsite_restic.py"
        self.assertIn(stable, BACKUP_UNIT)
        self.assertIn(stable, RESTORE_UNIT)
        self.assertNotIn("/srv/portal/current/ops/portal_offsite_restic.py", BACKUP_UNIT + RESTORE_UNIT)

    def test_installer_requires_exact_current_main(self):
        self.assertIn('[[ "$SHA" =~ ^[0-9a-f]{40}$ ]]', INSTALL)
        self.assertIn("ls-remote origin refs/heads/main", INSTALL)
        self.assertIn('[[ "$remote_sha" == "$SHA" ]]', INSTALL)
        self.assertIn('git -C "$REPO" archive "$SHA"', INSTALL)

    def test_installer_creates_isolated_identity_and_read_only_acl(self):
        self.assertIn("groupadd --system portal-backup-readers", INSTALL)
        self.assertIn("useradd --system --gid portal-backup-readers", INSTALL)
        self.assertIn("setfacl -R -m g:portal-backup-readers:r-X", INSTALL)
        self.assertIn("d:g:portal-backup-readers:r-X", INSTALL)

    def test_installer_never_activates_offsite_timers(self):
        self.assertIsNone(re.search(r"systemctl\s+(?:enable|start|restart|enable\s+--now)\s+portal-offsite", INSTALL))
        self.assertIn("were NOT enabled or started", INSTALL)

    def test_acl_install_is_explicit(self):
        self.assertIn("--install-acl", INSTALL)
        self.assertIn("apt-get install -y --no-install-recommends acl", INSTALL)

    def test_installer_is_committed_executable(self):
        mode = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-s", "ops/install_offsite_backup_ubuntu.sh"],
            text=True,
        ).split()[0]
        self.assertEqual(mode, "100755")

if __name__ == "__main__":
    unittest.main()
