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
    r'0\.0\.0\.0:3002',
    r'0\.0\.0\.0:3001',
    r'0\.0\.0\.0:9090',
    r'0\.0\.0\.0:9093',
]:
    if re.search(forbidden, compose):
        errors.append(f"public management bind forbidden: {forbidden}")

for expected in [
    "quay.io/prometheus/prometheus:v3.15.0",
    "quay.io/prometheus/node-exporter:v1.12.1",
    "quay.io/prometheus/blackbox-exporter:v0.28.0",
    "quay.io/prometheus/alertmanager:v0.34.1",
    "grafana/grafana:13.2.3",
    "ghcr.io/louislam/uptime-kuma:2.5.5",
]:
    if expected not in compose:
        errors.append(f"unpinned or missing image: {expected}")

prom = (ROOT / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
for endpoint in [
    "https://178.209.127.247:8443/api/ping",
    "https://178.209.127.247:8443/api/ready",
    "https://178.209.127.247/web/",
]:
    if endpoint not in prom:
        errors.append(f"missing origin endpoint: {endpoint}")

for logical_endpoint in [
    "https://api.vart-portal.ru/api/ping",
    "https://api.vart-portal.ru/api/ready",
    "https://vart-portal.ru/web/",
]:
    if logical_endpoint not in prom:
        errors.append(f"missing logical endpoint label: {logical_endpoint}")

if "178.209.127.247:22" not in prom or "module: [ssh_banner]" not in prom:
    errors.append("missing direct SSH banner probe")
if "api.vart-portal.ru:22" in prom:
    errors.append("Cloudflare-proxied hostname must not be used for the SSH banner probe")
if "http_api_origin_2xx" not in prom or "http_site_origin_2xx" not in prom:
    errors.append("missing direct-origin blackbox modules")

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
