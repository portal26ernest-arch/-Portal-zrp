# PORTAL

PORTAL combines a Python Server/API, shared Web UI and native client shells.
The canonical requirements and task status are in [PORTAL_MASTER_ROADMAP.md](PORTAL_MASTER_ROADMAP.md).
Read [AGENTS.md](AGENTS.md) before development; release integrity rules are separate from local testing.

## Source layout

- `server/`: HTTP API, authorization, tenant storage boundary, documents, payroll and business services.
- `android_src/app/src/main/assets/`: shared Web UI used by Web, Android, iOS and Windows Desktop.
- `desktop_windows/`: current WPF/WebView2 Desktop, encrypted local cache/outbox and update verification.
- `android_src/` and `ios_src/`: native mobile shells; shared UI changes require parity checks.
- `desktop/windows/`: older Edge/browser launcher, not the current WPF client.
- `deploy/` and `ops/`: deployment and operational tooling; do not run against live infrastructure during local development.

## Isolated Codex development

Use the published cloud environment's saved setup/start instructions. Its local helper uses
`/workspace/.portal-cloud-safe`, synthetic SQLite and `127.0.0.1:18765`; it does not use production data.
Run the helper in the existing checkout without disabling its environment, provenance or socket checks.

```sh
/workspace/.portal-cloud-safe/venv/bin/python -I -B /workspace/.portal-cloud-safe/control.py check
/workspace/.portal-cloud-safe/venv/bin/python -I -B /workspace/.portal-cloud-safe/control.py start
```

Keep `start` in its own managed session, then run `control.py smoke` from another session.
The saved helper's `test` command runs a fixed onboarding subset, not every development test or newly added test.
Additional tests must run in an explicitly cleaned environment with reviewed local modules only;
do not copy the historical broad `unittest discover` commands with inherited PostgreSQL/VPS flags.
Never point the fixture at a working database or supply working API keys.

See [the cloud source audit](docs/PORTAL_CLOUD_AUDIT_20261011.md) for findings,
regression coverage and unverified native/network gates. Local test success is not deployment evidence.
