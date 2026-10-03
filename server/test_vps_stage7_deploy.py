"""Offline safety contracts for the Stage 7 staging deploy and Windows runner."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / "server" / "vps_stage7_staging_deploy.sh").read_text(encoding="utf-8")
RUNNER = (ROOT / "tools" / "run_stage7.ps1").read_text(encoding="utf-8")
BANNER_RELAY = (ROOT / "tools" / "ssh_banner_first_relay.py").read_text(encoding="utf-8")
PG_INTEGRATION = (ROOT / "server" / "test_postgresql_integration.py").read_text(encoding="utf-8")


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

    def test_deploy_runs_allowlisted_stage7_tenant_api_and_restart_gate(self):
        self.assertIn('PORTAL_PG_INTEGRATION=1', DEPLOY)
        self.assertIn('PORTAL_PG_TEST_ENV_FILE="$ENV_FILE"', DEPLOY)
        self.assertIn('PORTAL_PG_EXPECTED_SERVICE="$SERVICE"', DEPLOY)
        self.assertIn('unittest -v test_postgresql_integration', DEPLOY)
        self.assertIn("('portal_test_stage7_staging', '8770', 'portal-stage7.service')", PG_INTEGRATION)
        self.assertIn("setval(pg_get_serial_sequence('companies','id')", DEPLOY)

    def test_database_and_api_are_loopback_only(self):
        self.assertIn('PORTAL_APP_HOST=127.0.0.1', DEPLOY)
        self.assertIn('ss -ltn | grep -q "127.0.0.1:$API_PORT"', DEPLOY)
        self.assertIn('ss -ltn | grep -Eq "0\\.0\\.0\\.0:5432|\\[::\\]:5432"', DEPLOY)

    def test_stage7_installs_canonical_server_runtime_dependencies(self):
        self.assertIn('pip" -q install -r "$REPO/server/requirements.txt" "psycopg[binary]"', DEPLOY)
        requirements = (ROOT / "server" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("openpyxl==3.1.5", requirements)
        self.assertIn("reportlab==5.0.1", requirements)

    def test_runtime_service_is_unprivileged_and_hardened(self):
        for directive in ('User=portal-stage7', 'NoNewPrivileges=true', 'ProtectSystem=full',
                          'ProtectKernelTunables=true', 'RestrictSUIDSGID=true', 'UMask=0077'):
            with self.subTest(directive=directive):
                self.assertIn(directive, DEPLOY)

    def test_setup_bootstrap_uses_generated_local_secret(self):
        self.assertIn('SETUP_TOKEN="$(openssl rand -hex 32)"', DEPLOY)
        self.assertIn('PORTAL_SETUP_TOKEN=$SETUP_TOKEN', DEPLOY)
        self.assertIn('X-Portal-Setup-Token: $SETUP_TOKEN', DEPLOY)

    def test_https_proxy_blocks_external_setup_and_has_renewal_reload_hook(self):
        self.assertGreaterEqual(DEPLOY.count('location = /api/setup'), 2)
        self.assertIn('return 403;', DEPLOY)
        self.assertIn('renewal-hooks/deploy/portal-stage7-nginx-reload', DEPLOY)
        self.assertIn('PILOT_SSLIP', DEPLOY)
        self.assertIn('CLOUDFLARED_BIN="$(command -v cloudflared)"', DEPLOY)
        self.assertIn('ExecStart=$CLOUDFLARED_BIN tunnel', DEPLOY)
        self.assertIn('if [[ "$PILOT_TUNNEL" == "1" && -z "$DOMAIN" ]]; then', DEPLOY)

    def test_runner_uses_pinned_host_key_commit_and_verifies_remote_report(self):
        for token in ('StrictHostKeyChecking=yes', 'UserKnownHostsFile=', 'IdentityFile',
                      'IdentitiesOnly=yes', 'ServerAliveCountMax=2', 'EXPECTED_COMMIT=$commit',
                      'PORTAL_STAGE7_DOMAIN=$Domain', 'PORTAL_STAGE7_PILOT_SSLIP=$sslipPilot',
                      'PORTAL_STAGE7_PILOT_TUNNEL=$tunnelPilot', 'UseBannerRelay = $true',
                      'Start-Process -FilePath $python', '-WindowStyle Hidden',
                      'replace "`r`n", "`n"', 'UTF8Encoding]::new($false)',
                      'scp @scpArgs $transferScript',
                      'HTTPS pilot mode: $pilotMode', 'foreach ($attempt in 1..5)',
                      'Start-Sleep -Seconds $delay',
                      'HostKeyAlias=$HostKeyAlias', 'Stop-Process -Id $relayProcess.Id',
                      'STAGE7_RESULT.txt', '-replace "`r", ""',
                      'production_database_touched=no', 'https_status=ok'):
            with self.subTest(token=token):
                self.assertIn(token, RUNNER)
        self.assertNotIn('StrictHostKeyChecking=no', RUNNER)
        self.assertNotIn('--doh-url', RUNNER)
        self.assertGreaterEqual(RUNNER.count("$ErrorActionPreference = 'Continue'"), 2)
        self.assertGreaterEqual(RUNNER.count("$ErrorActionPreference = $previousErrorActionPreference"), 2)

    def test_explicit_domain_wins_and_sslip_is_default_pilot(self):
        self.assertIn('[string]$Domain', RUNNER)
        self.assertIn("$sslipPilot = if ($Domain -or $UseCloudflareTunnel) { '0' } else { '1' }", RUNNER)
        self.assertIn("$tunnelPilot = if ($UseCloudflareTunnel) { '1' } else { '0' }", RUNNER)

    def test_banner_first_relay_waits_for_server_identification(self):
        for token in (
            'REMOTE = ("178.209.127.247", 22)',
            'LISTEN = ("127.0.0.1", 2223)',
            'server_line = recv_line(remote)',
            'client.sendall(server_line)',
            'client_line = recv_line(client)',
            'remote.sendall(client_line)',
        ):
            with self.subTest(token=token):
                self.assertIn(token, BANNER_RELAY)
        self.assertNotIn('BEGIN OPENSSH PRIVATE KEY', BANNER_RELAY)
        self.assertNotIn('StrictHostKeyChecking=no', BANNER_RELAY)


if __name__ == "__main__":
    unittest.main()
