"""Offline safety contracts for the Stage 7 staging deploy and Windows runner."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / "server" / "vps_stage7_staging_deploy.sh").read_text(encoding="utf-8")
RUNNER = (ROOT / "tools" / "run_stage7.ps1").read_text(encoding="utf-8")


class Stage7DeploySafetyTests(unittest.TestCase):
    def test_deploy_is_test_database_only_and_never_targets_production(self):
        self.assertIn('DB="portal_test_stage7_staging"', DEPLOY)
        self.assertIn('[[ "$DB" == portal_test_stage7_* ]]', DEPLOY)
        self.assertIn('production_database_touched=no', DEPLOY)

    def test_deploy_requires_exact_pinned_commit_in_verified_branch(self):
        self.assertIn('PORTAL_STAGE7_EXPECTED_COMMIT', DEPLOY)
        self.assertIn('git -C "$REPO" fetch --prune origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"', DEPLOY)
        self.assertIn('git -C "$REPO" merge-base --is-ancestor "$EXPECTED_COMMIT" "origin/$BRANCH"', DEPLOY)
        self.assertIn('git -C "$REPO" checkout --detach "$EXPECTED_COMMIT"', DEPLOY)
        self.assertNotIn('reset --hard', DEPLOY)

    def test_deploy_refuses_parallel_or_dirty_checkout_overwrite(self):
        self.assertIn('flock -n 9', DEPLOY)
        self.assertIn('git -C "$REPO" status --porcelain', DEPLOY)
        self.assertIn('refusing to overwrite local files', DEPLOY)

    def test_migrations_are_recorded_by_version_and_checksum(self):
        self.assertIn('CREATE TABLE IF NOT EXISTS portal_stage7_schema_migrations', DEPLOY)
        self.assertIn('checksum TEXT NOT NULL', DEPLOY)
        self.assertIn('sha256sum "$migration_file"', DEPLOY)
        self.assertIn('migration checksum изменился после применения', DEPLOY)
        self.assertIn('INSERT INTO portal_stage7_schema_migrations(version,checksum)', DEPLOY)

    def test_database_and_api_are_loopback_only(self):
        self.assertIn('PORTAL_APP_HOST=127.0.0.1', DEPLOY)
        self.assertIn('ss -ltn | grep -q "127.0.0.1:$API_PORT"', DEPLOY)
        self.assertIn('ss -ltn | grep -Eq "0\\.0\\.0\\.0:5432|\\[::\\]:5432"', DEPLOY)

    def test_runtime_service_is_unprivileged_and_hardened(self):
        for directive in ('User=portal-stage7', 'NoNewPrivileges=true', 'ProtectSystem=full',
                          'ProtectKernelTunables=true', 'RestrictSUIDSGID=true', 'UMask=0077'):
            with self.subTest(directive=directive):
                self.assertIn(directive, DEPLOY)

    def test_https_proxy_blocks_external_setup_and_has_renewal_reload_hook(self):
        self.assertGreaterEqual(DEPLOY.count('location = /api/setup'), 2)
        self.assertIn('return 403;', DEPLOY)
        self.assertIn('renewal-hooks/deploy/portal-stage7-nginx-reload', DEPLOY)
        self.assertIn('PILOT_SSLIP', DEPLOY)

    def test_runner_uses_pinned_host_key_commit_and_verifies_remote_report(self):
        for token in ('StrictHostKeyChecking=yes', 'UserKnownHostsFile=', 'IdentityFile',
                      'IdentitiesOnly=yes', 'ServerAliveCountMax=2', 'EXPECTED_COMMIT=$commit',
                      'PORTAL_STAGE7_PILOT_SSLIP=1', 'STAGE7_RESULT.txt',
                      'production_database_touched=no', 'https_status=ok'):
            with self.subTest(token=token):
                self.assertIn(token, RUNNER)
        self.assertNotIn('StrictHostKeyChecking=no', RUNNER)


if __name__ == "__main__":
    unittest.main()
