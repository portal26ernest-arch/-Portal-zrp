# PORTAL security review — 2026-10-04

## Result

Static source review at `a252adc33689f34dbd3f66c7d124264f39108a7a` confirmed four security weaknesses. Detailed source review covered prioritized authentication/bootstrap, tenant API/RLS, documents/Excel/PDF, shared Web paths, selected client shells, Desktop update handling, and release/operations workflows. The repository inventory contained 284 files; this was a partial review, not an exhaustive audit of every file.

No production service, VPS mirror, database, secrets, or release settings were changed. The application was not executed for this security review.

## Findings and priority

### P1 — Tenant PIN login has no online throttling

`server/portal_app_server.py:892-916` verifies login attempts, logs a failure and returns 401 without an application-level counter, delay, or lockout. `server/employee_identity.py:201-206` allows a four-character minimum PIN. A successful guess grants that account's tenant permissions. PBKDF2 raises per-guess cost but does not limit online attempts. External edge throttling was not inspected.

**Risk:** repeated PIN guessing can eventually yield an account session. Add account- and source-based throttles, progressive delay, bounded lockout and monitoring; test that rotating source addresses do not bypass per-account limits.

### P1 — Desktop updater does not independently authenticate downloaded packages

`desktop_windows/MainWindow.xaml.cs:477-495,536-582` accepts HTTPS package URLs and verifies a downloaded ZIP against a SHA-256 supplied by the same manifest, then installs and launches it. `server/desktop_update.py` supplies the configured URL and digest. No package signature or pinned publisher check is present.

**Risk:** if the update manifest/server is compromised, an attacker can provide a malicious archive and matching digest. The user must accept the update prompt. Sign the manifest/package with a key pinned in the client or verify Authenticode against an explicit publisher identity; restrict update origins and fail closed.

### P2 — First-user bootstrap relies on the reverse proxy's loopback address

`server/portal_app_server.py:1251-1264` permits setup when `self.client_address` is loopback and creates the first user/session when the tenant has no users. `deploy/nginx/portal.conf.template:29-37` proxies public requests to `127.0.0.1`, so the application sees the proxy as the peer.

**Risk:** a remote unauthenticated caller can race first-time provisioning on an empty tenant. This is conditional on the setup window; the current production configuration/account state was not verified. Require a one-time setup secret or authenticated provisioning token and permanently close setup after provisioning.

### P2 — Release workflows do not verify tag signatures

`.github/workflows/android-release.yml:10-15,32-39` triggers on matching release tags, has `contents:write`, and accepts the tag prefix as sufficient in the “signed release tag” guard. `.github/workflows/windows-desktop.yml:81-85,98-107` similarly gates publishing by tag/version pattern without cryptographic verification.

**Risk:** a principal able to create/move a matching tag may feed unreviewed code into release publishing if external GitHub controls do not prevent it. GitHub rulesets, repository write access and environment approvals were not inspected. Verify signed annotated tags against a pinned key, restrict tag changes, bind builds to reviewed SHAs, and protect signing/publishing secrets behind required environments.

## Remediation status — 2026-10-04

- Tenant login: закрыт application-level `LoginLimiter` с отдельными budget по source IP и account/principal; forwarded identity принимается только от явно доверенных proxy.
- Desktop updater: manifest подписывается RSA-3072 release key, public key закреплён в Desktop-клиенте; ZIP принимается только после проверки подписи manifest + SHA-256 + ограничений origin/redirect.
- Bootstrap: публичный Nginx блокирует `/api/setup`, backend дополнительно требует фактическую loopback identity и отклоняет удалённый `X-Real-IP` через локальный reverse proxy.
- Release tag injection: вместо доверия к подписи входящего тега release workflows переводятся на более узкую модель — release нельзя запустить push-тегом вообще. Android/Desktop публикация запускается только вручную из текущего `main`, SHA перепроверяется перед signing/publish, а существующий tag/release приводит к fail-closed отказу без замены assets. Поэтому создание/перемещение matching tag больше не является входом в release pipeline. GitHub repository rulesets/environment approvals остаются полезной внешней defense-in-depth настройкой и отдельно не подтверждены доступными инструментами.

Кандидат hardening: `assistant/release-control-hardening-20261004`. До статуса «интегрировано» обязательны push, полный GitHub CI и fast-forward/merge в `main`.

## Reviewed areas without confirmed findings

- Selected tenant routing, company authorization, PostgreSQL RLS context and session lifecycle.
- Documents, Excel import/apply, PDF and invoice exchange paths.
- Selected shared Web UI, DOM rendering, static serving and API adapter.
- Systemd/Nginx templates, source-mirror guard and backup scripts, apart from the findings above.

These statements apply only to the reviewed source paths and do not establish absence of vulnerabilities elsewhere.

## Coverage limits and follow-up

- Detailed review was prioritized across a 284-file inventory. Marketplace/news modules, reminder workers, migration utilities, ancillary helpers and other remaining files were not all reviewed.
- No live production Nginx configuration, current setup/account state, GitHub rulesets, secret/environment protections or active Desktop update manifest was inspected.
- Desktop “Тарифы” UI accessibility and speed were not measured. The available Computer Use interaction reported that it had been stopped by physical Escape; no further UI control was attempted. Earlier endpoint evidence recorded `/api/ping` and `/api/ready` as 200 while Web paths returned 401/404, inconsistent with prior asset smoke. Reconcile the active production endpoint before a Desktop user-flow check.
- No exploitation or dynamic security test was run; findings are source-backed static traces.

## Next actions

1. Implement tenant login throttling and add regression tests.
2. Add independently verifiable signatures to Desktop update metadata/packages.
3. Add one-time authenticated bootstrap and test it through the actual reverse proxy.
4. Verify GitHub tag rulesets and implement signature verification in both release workflows.
5. Inspect live production/GitHub update configuration and complete review of remaining source inventory.
6. Reconcile production Web asset responses, then perform the Desktop tariff smoke and timing measurement when UI capture is available.
