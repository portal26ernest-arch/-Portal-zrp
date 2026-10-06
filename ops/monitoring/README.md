# PORTAL self-hosted monitoring

This directory contains the PORTAL-owned monitoring stack.

## Components

- Uptime Kuma 2.5.5 — operator-friendly uptime/status view.
- Prometheus 3.15.0 — metrics and alert-rule evaluation.
- node_exporter 1.12.1 — host CPU/RAM/disk/load metrics.
- blackbox_exporter 0.28.0 — HTTP/TLS probes for PORTAL public endpoints.
- Alertmanager 0.34.1 — alert grouping/routing.
- Grafana 13.3.0 — private dashboard.

All management UIs bind to loopback only by default. Do not expose ports 3000, 3001, 9090, or 9093 directly to the Internet.

## Monitored endpoints

The declarative Prometheus probes cover:
- https://api.vart-portal.ru/api/ping
- https://api.vart-portal.ru/api/ready
- https://vart-portal.ru/web/
- https://reserve-api.vart-portal.ru/api/ping

Uptime Kuma should mirror these checks plus certificate-expiry checks. Prometheus remains the canonical declarative probe/rule source because Uptime Kuma monitor management uses an internal API whose compatibility is not guaranteed.

## Secrets

Create /etc/portal-monitoring/secrets/grafana_admin_password on the monitoring host with mode 0600. Never commit the password.

Copy .env.example to .env only on the host if overrides are needed.

## Validation

Run from this directory:

    python3 validate_monitoring.py
    docker compose config --quiet
    docker run --rm -v "$PWD/prometheus:/etc/prometheus:ro" prom/prometheus:v3.15.0 promtool check config /etc/prometheus/prometheus.yml
    docker run --rm -v "$PWD/prometheus:/etc/prometheus:ro" prom/prometheus:v3.15.0 promtool check rules /etc/prometheus/rules/portal.rules.yml
    docker run --rm -v "$PWD/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.34.1 amtool check-config /etc/alertmanager/alertmanager.yml

## Deployment safety

1. Deploy from a pushed Git SHA/branch only.
2. Keep monitoring data in named Docker volumes.
3. Do not publish internal monitoring ports externally.
4. Configure notification credentials outside Git.
5. A second independent monitoring host is still required for true detection of total primary-VPS loss. Until that exists, the ChatGPT hourly external watchdog is a supplementary independent check, not a replacement for a second owned host.

## Access

From an authorized workstation, use SSH port forwarding when the VPS SSH transport is available:

    ssh -L 3000:127.0.0.1:3000 -L 3001:127.0.0.1:3001 portal-vps

Then open Grafana at http://127.0.0.1:3000 and Uptime Kuma at http://127.0.0.1:3001.
