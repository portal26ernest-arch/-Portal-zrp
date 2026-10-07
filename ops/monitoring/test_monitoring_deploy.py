from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DEPLOY = (ROOT / "deploy_ubuntu.sh").read_text(encoding="utf-8")


class MonitoringDeploymentGuards(unittest.TestCase):
    def test_management_ports_are_loopback_only(self) -> None:
        for port in (3000, 3001, 9090, 9093):
            line = next(line for line in COMPOSE.splitlines() if f":{port}:{port}" in line)
            self.assertIn(f'"127.0.0.1:{port}:{port}"', line)
            self.assertNotIn("0.0.0.0", line)

    def test_images_have_fixed_versions(self) -> None:
        images = re.findall(r"^\s+image:\s+(\S+)", COMPOSE, re.MULTILINE)
        self.assertEqual(len(images), 6)
        for image in images:
            self.assertIn(":", image)
            self.assertFalse(image.endswith(":latest"))
            self.assertRegex(image.rsplit(":", 1)[1], r"^v?[0-9]+\.[0-9]+")

    def test_no_secret_value_or_default_password_is_tracked(self) -> None:
        tracked = [p for p in ROOT.rglob("*") if p.is_file() and p.name != "test_monitoring_deploy.py" and p.suffix != ".pyc" and "__pycache__" not in p.parts]
        forbidden = (b"GF_SECURITY_ADMIN_PASSWORD=", b"grafana_admin_password: ", b"password123")
        for path in tracked:
            data = path.read_bytes()
            for value in forbidden:
                self.assertNotIn(value, data, f"secret-like value in {path.relative_to(ROOT)}")

    def test_exact_sha_required_and_remote_push_verified(self) -> None:
        self.assertIn('[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "a full exact 40-character Git SHA is required"', DEPLOY)
        self.assertIn('git -C "$REPO" ls-remote origin', DEPLOY)
        self.assertIn('[[ "$(git -C "$REPO" rev-parse HEAD)" == "$SHA" ]]', DEPLOY)
        self.assertIn('git -C "$REPO" status --porcelain --untracked-files=all', DEPLOY)

    def test_deploy_is_explicit_and_preflight_fails_closed(self) -> None:
        self.assertIn("--deploy", DEPLOY)
        self.assertIn("--install-docker", DEPLOY)
        self.assertIn('(( DEPLOY == 0 ))', DEPLOY)
        self.assertIn('[[ -s "$secret" ]] || fail', DEPLOY)
        self.assertIn('docker compose -f "$payload/docker-compose.yml"', DEPLOY)
        self.assertIn("promtool check config", DEPLOY)
        self.assertIn("promtool check rules", DEPLOY)
        self.assertIn("amtool check-config", DEPLOY)
        self.assertIn("--config.check", DEPLOY)
        self.assertIn("download.docker.com/linux/ubuntu", DEPLOY)
        self.assertNotIn("get.docker.com", DEPLOY)

    def test_static_monitoring_validator_runs(self) -> None:
        result = subprocess.run(["python", str(ROOT / "validate_monitoring.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
