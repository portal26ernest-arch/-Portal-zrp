# PORTAL production cutover report — 2026-10-02

## A. Decision

| Gate | Result | Evidence / reason |
|---|---|---|
| Production ready | **NO** | Final source, account reconciliation, owned domain, dedicated production roles, off-server backup and signed Android release remain open. |
| Cutover | **NO** | No final write freeze, import, client switch or production write smoke occurred. |
| HTTPS production hostname | **NO** | Trusted TLS and HTTP→HTTPS work on a temporary `sslip.io` hostname; no owned API hostname is configured. |
| Android production | **NO** | Current metadata is `3.5-dev` / versionCode 35, staging only. Release requires a protected signing workflow and approved stable HTTPS API URL. |
| PostgreSQL master | **NO** | Split PostgreSQL candidate is online, but the authoritative final source and Android switch are unconfirmed. |
| Tenant isolation | **PARTIAL** | Runtime role/table boundary and 48 FORCE RLS tables pass; disposable two-company PostgreSQL E2E is green. Production still reuses Stage 7 runtime roles and has one registered company. |
| Backup + restore | **YES for on-server rehearsal** | Fresh control and tenant dumps restored into isolated databases and counts/RLS matched. Off-server copy remains open. |

Starting workspace: `bd059b2100ffba08acc6f21f88070ec9ae977c0c` on `assistant/god-global-role-20261002`; one untracked task file was preserved. The pre-existing `2375a8b` split-DB commit was integrated by cherry-pick into `codex/production-cutover`. Deployed API source: `af663a8c207ba45ed0f0d99dd6364178265cb85c`. Final branch HEAD is the Git commit containing this report and subsequent documentation; use `git rev-parse HEAD` or the final task response.

## B. VPS architecture and service

- Ubuntu VPS runs `portal-production.service` as unprivileged `portal-production`, enabled with `Restart=on-failure`; API binds only `127.0.0.1:8790`. The current source is pinned by `ops/systemd/portal-production-cutover.conf`, with the prior unit/release retained for rollback.
- Nginx accepts 80/443 and forwards the temporary HTTPS hostname; HTTP redirects to HTTPS. `/api/ping` and the new `/api/ready` respond. Two successive service restarts returned to `active/running`, `NRestarts=0`. A full host reboot was not performed.
- PostgreSQL listens on loopback `127.0.0.1/[::1]:5432`. UFW exposes 22, 80 and 443; monitoring port 10050 is limited to pre-existing monitoring addresses. Other PORTAL API ports listen on loopback.
- The last runtime journal contained no credential-bearing connection string or token. API exception responses use a generic 500; `/api/ready` returns only `ready=true` or a generic 503. Forced PostgreSQL outage was not simulated on the shared VPS, because it would interrupt other services; the readiness failure/recovery path is covered by a test.

## C. Control and tenant PostgreSQL

`portal_prod_control` holds the company registry, Platform Owner and context key. `portal_prod_company_1` holds Company 1 business data. The production environment explicitly selects PostgreSQL and separate DB URLs; startup rejects SQLite fallback, same/test database names, identical runtime roles, over-privileged roles, missing schema and missing FORCE RLS. The production startup preflight passed under the actual runtime user. Both runtime roles have no SUPERUSER, BYPASSRLS, CREATEDB or CREATEROLE; the control role cannot SELECT `app_users` and the tenant role cannot SELECT `companies` or `portal_company_keys` in their respective databases.

**Remaining security work:** both production URLs currently authenticate as `portal_stage7_control` / `portal_stage7_tenant`. Their table grants in the production databases are separated, but the roles are also used by Stage 7. Rotate to dedicated production-only roles, revoke their production access, and retest the complete API before accepting production traffic.

## D. Schema and migration

No production schema migration or data import was applied in this task. The existing split tenant reports runtime schema v1, RLS context schema v1 and 10 applied company migration rows through v13. Startup validates those markers and the required tables/triggers without creating tables. Company 1 is active in the control registry. No production data was deleted or rewritten.

## E. Reconciliation

`PORTAL_PRODUCTION_RECONCILIATION.json` is the machine-readable comparison. The older VPS `portal_production` is a **comparison candidate**, not a confirmed canonical source. Company 1 has matching full-row hashes for employees 4, clients 39, operations 78, tariff versions 403, work 8 and products 47. Payroll closures, settlement entries, materials/movements, invoices and document metadata are zero in both candidates. Client-operation orphans, legacy work/employee orphans and case-insensitive duplicate logins in the split DB are zero.

**Blocking difference:** older VPS Company 1 has **5 app users (3 admins, 2 managers)**; the split tenant has **4 (2 admins, 2 managers)**. The full-row hash differs. The older VPS database also contains other companies; their provenance was not assumed. No fresh post-freeze phone/source snapshot or independent approval of source lineage was available. Therefore the final import, financial reconciliation and Android switch were not performed.

## F. Tests and CI

| Check | Result |
|---|---|
| Local full backend (`python -m unittest discover -s server -p 'test_*.py' -q`) | 314 run, 0 failed, 49 skipped. |
| Local targeted API/config | API 19/19, config/import 8/8; syntax compilation passed after the startup-log adjustment. |
| Local ops contracts | 10/10 passed; backup Bash syntax passed. |
| Android/JS (`node --test android_src/tests/*.test.cjs`) | 58/58 passed, 0 skipped. |
| Disposable PostgreSQL | Two-company/RLS suite passed in [Web CI at `41b56b0`](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36936393394) and [deployed-code Web CI at `af663a8`](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36937196994). The earlier isolated VPS reproduction ran 36 tests with 2 gated skips and exposed one stale audit assertion; disposable DB/roles/temp cleanup was confirmed. The corrected CI suite passed. |
| Server CI | [Deployed-code Server CI](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36937197141) and [unit-override Server CI](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36937330328) succeeded. |
| Android UI / staging APK CI | [UI](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36935685562) and [staging APK](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36935685550) succeeded at `ea6dd28`; later commits did not change Android source. Signed production release was not run. |

The first new Web run failed because an inherited PostgreSQL test still filtered `owner_login`/`technical_access` after the existing God audit change wrote `god_login`/`god_access`. The test was corrected without disabling assertions; subsequent PostgreSQL CI passed. Local full-suite warnings include existing `ResourceWarning` messages for SQLite test connections, `datetime.utcnow()` deprecations and one openpyxl default-style warning. Those warnings did not fail tests and require a separate fixture cleanup; no production connection leak was demonstrated.

## G. Backup and restore

- Fresh private `pg_dump -Fc` files for `portal_prod_control` (399,344 bytes) and `portal_prod_company_1` (460,110 bytes) passed SHA-256 verification and `pg_restore --list`. They remain on the VPS outside Git.
- Each dump was restored to a separate `portal_test_restore_*` database. Control counts matched: 1 company, 1 owner, 1 key. Tenant counts matched: 4 employees, 4 users, 39 clients, 8 work rows; the broader category counts matched `PORTAL_PRODUCTION_RECONCILIATION.json`, and 48 FORCE RLS tables survived restore. The two temporary restore databases were removed after verification.
- `portal-central-backup.timer` is active/enabled. Its tested service now uses the versioned `ops/portal_central_backup.sh` and produced fresh dumps of the split control, split tenant, older production and staging databases plus central storage. It logged `BACKUP_SUCCESS=1 RETENTION_DAYS=14`; retention touches only daily directories and preserves manual cutover checkpoints. The previous backup script was retained on the VPS.
- No independent off-server destination was supplied or tested. Item 93 remains open.

## H. Security checks

The tracked repository contains no private key, PAT or token marker detected by the focused scan; only `.env.example` matches secret-like filename rules. No production password, PIN, session token, signing key, SSH key or DB connection value was printed or committed. The two tracked DSN pattern matches are the disposable CI password and a Stage 7 environment-template expansion, not production credential values. Android source/assets contain no tracked credential-bearing DSN. Production EnvironmentFile remains root-owned mode 0600 in a mode 0700 directory. Android release Gradle now rejects local, IP, `sslip.io`, Quick Tunnel, missing and non-HTTPS endpoints even if invoked outside GitHub Actions.

## I. Android production status

Current source metadata: `versionName=3.5-dev`, `versionCode=35`, `buildNumber=3.5`, development channel. The staging APK and UI checks passed. Release workflow requires a stable HTTPS URL and protected GitHub signing inputs; the release task has a second URL guard in Gradle. A signed production APK was not built or published; the phone was not used as a test server. Do not increase to a release number until final source, domain, signing and cutover gates pass. The next completed build under the 3.x sequence would be 3.6.

## J. Rollback

The prior production service code, base unit and first drop-in are retained. For an API-code rollback, stop `portal-production.service`, copy `/etc/portal-production/portal-production-cutover.previous.conf` over `/etc/systemd/system/portal-production.service.d/10-portal-cutover.conf`, run `systemctl daemon-reload`, start the service, then verify `/api/ready`, `/api/ping`, role-scoped auth and tenant boundaries. Preserve both sets of dumps and journal evidence. The current service has not accepted a declared cutover, so **do not restore a database merely to roll back this code change**.

For a future data cutover rollback: stop writes first; preserve and reconcile every new VPS write; use the verified pre-cutover dump only after selecting the correct control and tenant restore pair and checking row counts, financial totals and RLS. Restore into an isolated target before changing the live database. Never delete fresh backups or re-enable two writable masters.

## K. Remaining release blockers and next action

1. Owner provides an owned API FQDN and DNS A record to the verified VPS address (and AAAA only if IPv6 is intentionally used). Configure Nginx/certificate renewal for that exact name, confirm external HTTPS and HTTP→HTTPS, then replace the temporary URL in server and protected Android release inputs.
2. Obtain a fresh authoritative snapshot after stopping legacy writes. Establish its lineage, reconcile all critical counts/IDs/financial facts and explain the missing admin before final import. Keep old and split databases untouched until this is resolved.
3. Configure a protected independent off-server backup destination and verify an isolated restore from that copy. Rotate Stage 7 roles out of the production URLs.
4. Configure protected Android release signing/API inputs, produce a signed 3.6 candidate through GitHub Actions, and verify the supported install/update and authenticated Company 1/Platform Owner smoke. Only then perform final read/write cutover and post-restart checks.

**PRODUCTION READY: NO. CUTOVER: NO.** The VPS service is running safely as a candidate; real production cutover is blocked by the items above.
