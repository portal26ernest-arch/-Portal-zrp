from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    ROOT / "docker-compose.yml",
    ROOT / "prometheus" / "prometheus.yml",
    ROOT / "prometheus" / "rules" / "portal.rules.yml",
    ROOT / "blackbox" / "blackbox.yml",
    ROOT / "alertmanager" / "alertmanager.yml",
    ROOT / "grafana" / "provisioning" / "datasources" / "prometheus.yml",
    ROOT / "grafana" / "provisioning" / "dashboards" / "dashboards.yml",
    ROOT / "grafana" / "dashboards" / "portal-overview.json",
]

errors: list[str] = []

for path in REQUIRED:
    if not path.is_file():
        errors.append(f"missing: {path.relative_to(ROOT)}")

compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
for forbidden in [
    r'0\.0\.0\.0:3000',
    r'0\.0\.0\.0:3001',
    r'0\.0\.0\.0:9090',
    r'0\.0\.0\.0:9093',
]:
    if re.search(forbidden, compose):
        errors.append(f"public management bind forbidden: {forbidden}")

for expected in [
    "prom/prometheus:v3.15.0",
    "prom/node-exporter:v1.12.1",
    "prom/blackbox-exporter:v0.28.0",
    "prom/alertmanager:v0.34.1",
    "grafana/grafana:13.3.0",
    "louislam/uptime-kuma:2.5.5",
]:
    if expected not in compose:
        errors.append(f"unpinned or missing image: {expected}")

prom = (ROOT / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
for endpoint in [
    "https://api.vart-portal.ru/api/ping",
    "https://api.vart-portal.ru/api/ready",
    "https://vart-portal.ru/web/",
    "https://reserve-api.vart-portal.ru/api/ping",
]:
    if endpoint not in prom:
        errors.append(f"missing endpoint: {endpoint}")

if "api.vart-portal.ru:22" not in prom or "module: [ssh_banner]" not in prom:
    errors.append("missing SSH banner probe")

dashboard = json.loads(
    (ROOT / "grafana" / "dashboards" / "portal-overview.json").read_text(encoding="utf-8")
)
if dashboard.get("uid") != "portal-overview":
    errors.append("Grafana dashboard UID mismatch")

if errors:
    for error in errors:
        print(f"ERROR: {error}")
    raise SystemExit(1)

print("PORTAL monitoring static validation: OK")
