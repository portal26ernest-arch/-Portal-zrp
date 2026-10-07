# PORTAL self-hosted monitoring

This directory contains the PORTAL-owned monitoring stack.

## Components

- Uptime Kuma 2.5.5 — operator-friendly uptime/status view.
- Prometheus 3.15.0 — metrics and alert-rule evaluation.
- node_exporter 1.12.1 — host CPU/RAM/disk/load metrics.
- blackbox_exporter 0.28.0 — HTTP/TLS probes for PORTAL public endpoints.
- Alertmanager 0.34.1 — alert grouping/routing.
- Grafana 13.2.3 — private dashboard.

All management UIs bind to loopback only by default. Do not expose ports 3002, 3001, 9090, or 9093 directly to the Internet.

## Monitored endpoints

The declarative Prometheus probes cover:
- https://api.vart-portal.ru/api/ping
- https://api.vart-portal.ru/api/ready
- https://vart-portal.ru/web/
- https://reserve-api.vart-portal.ru/api/ping
- SSH banner on api.vart-portal.ru:22 (must actually return SSH-2.0-, not merely accept TCP)

Uptime Kuma should mirror these checks plus certificate-expiry checks. Prometheus remains the canonical declarative probe/rule source because Uptime Kuma monitor management uses an internal API whose compatibility is not guaranteed.

## Secrets

Create `/etc/portal-monitoring/secrets/grafana_admin_password` on the monitoring host with mode 0600. Never commit the password. Optional Compose overrides may be supplied through a host-only `.env` file; no `.env` file is required by the checked-in configuration.

## Validation

Run from this directory:

    python3 validate_monitoring.py
    docker compose config --quiet
    docker run --rm --entrypoint /bin/promtool -v "$PWD/prometheus:/etc/prometheus:ro" quay.io/prometheus/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml
    docker run --rm --entrypoint /bin/promtool -v "$PWD/prometheus:/etc/prometheus:ro" quay.io/prometheus/prometheus:v3.15.0 check rules /etc/prometheus/rules/portal.rules.yml
    docker run --rm -v "$PWD/alertmanager:/etc/alertmanager:ro" quay.io/prometheus/alertmanager:v0.34.1 amtool check-config /etc/alertmanager/alertmanager.yml

## Ubuntu preflight and deployment

`deploy_ubuntu.sh` is a root-only, fail-closed workflow. It requires Ubuntu, at least 10 GiB free on `/srv`, at least 2 GiB RAM, a clean Git checkout whose `HEAD` is the supplied full SHA, and confirmation that the exact SHA is advertised by `origin`. It extracts the complete `ops/monitoring` directory with `git archive` from that commit; it does not copy a working tree. Existing version directories and Docker named volumes are retained. The active `current` symlink is switched only after the candidate passes config validation.

Create the Grafana password out-of-band before running the script. The secret must be at least 20 bytes, high-entropy, and stored at `/etc/portal-monitoring/secrets/grafana_admin_password` with restrictive permissions. The script never generates or prints the secret. It refuses a missing/weak secret. Docker installation is opt-in and uses only packages from Ubuntu plus Docker's official Ubuntu apt repository.

Preflight only (no stack start):

    sudo ops/monitoring/deploy_ubuntu.sh --repo /srv/portal-source/repo --sha <exact-pushed-40-char-sha>

Explicitly install Docker if absent and deploy:

    sudo ops/monitoring/deploy_ubuntu.sh --repo /srv/portal-source/repo --sha <exact-pushed-40-char-sha> --install-docker --deploy

The workflow validates Compose, Prometheus config/rules, Alertmanager and blackbox config before start. After start it checks local Grafana, Kuma, Prometheus and Alertmanager endpoints, then public PORTAL API/Web probes. No DNS or firewall rules are changed; published management ports remain bound to `127.0.0.1`. Logs: `cd /srv/portal-monitoring/current && docker compose logs --tail=100`.

Rollback keeps both SHA directories and all named volumes. The script prints the exact symlink rollback command after successful smoke; inspect the prior version and run Compose from `/srv/portal-monitoring/previous`. Do not remove old release directories or volumes as part of routine rollback.

The static/unit guards can be run on Windows or Linux with:

    python -m unittest ops.monitoring.test_monitoring_deploy
    python ops/monitoring/validate_monitoring.py

This is code-ready tooling only. Do not infer monitoring availability until a separately authorized runtime deployment and its local/public smoke complete. A second independent owned host remains an external gate for detection of total failure of the monitored VPS; monitoring software on the same host cannot detect that host's complete loss.

## Deployment safety

1. Deploy from a pushed Git SHA/branch only.
2. Keep monitoring data in named Docker volumes.
3. Do not publish internal monitoring ports externally.
4. Configure notification credentials outside Git.
5. A second independent monitoring host is still required for true detection of total primary-VPS loss. Until that exists, the ChatGPT hourly external watchdog is a supplementary independent check, not a replacement for a second owned host.

## Access

From an authorized workstation, use SSH port forwarding when the VPS SSH transport is available:

    ssh -L 3002:127.0.0.1:3002 -L 3001:127.0.0.1:3001 portal-vps

Then open Grafana at http://127.0.0.1:3002 and Uptime Kuma at http://127.0.0.1:3001.
