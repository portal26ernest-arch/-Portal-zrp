# PORTAL Finalization Part 12 — checkpoint report

**Status: IN PROGRESS; Definition of Done is not met.** This report is an evidence checkpoint, not a claim that all Part 12 requirements are finished.

Дата: 2026-09-30
Verified Part 11 base: `bc95a942021bb5c43d112f51d2c2e7881059b47a`
Current implementation HEAD when this checkpoint was prepared: `2b95dffe891d80244487bcc7fef9ce081acdc468`
Branch: `codex-finalization-megapack-part12`
Worktree: `C:\Users\darta\Documents\PORTAL-Finalization-Part12`

## Commits

- `1d3d7bb` — `Add-PORTAL-company-knowledge-for-Codex` (the requested `615495c` commit, limited to the three expected documents).
- `0cec960` — prepare the 3.5 staging candidate, safe branch triggers, readiness/runbook/checkpoint docs.
- `f963649` — payroll settlement events in a separate payroll XLSX «Выплаты» sheet.
- `8408a33` — make Android updater UI test fixtures version-aware.
- `fd51cc2` — publish staging APK SHA-256 in the workflow summary.
- `0eb573e` — include the APK hash in the public artifact name (first attempt exposed an artifact path/prefix mismatch).
- `2b95dff` — correct artifact upload to use stable local filenames and a separate hash-bearing artifact name.

## Implemented and verified in Part 12

- Payroll XLSX now contains a separate «Выплаты» sheet with employee, period, accrued, paid, balance, payment dates and totals. It reads append-only settlement events, leaves closed payroll snapshots unchanged, and keeps the existing summary/employee/detail sheets.
- Staging candidate advanced from 3.4/34 to `3.5-dev-staging`, versionCode `35`, buildNumber `3.5`. The staging workflow includes version metadata, changelog, APK checksum and validation report; the artifact name includes the APK SHA-256. Production release workflow was not run.
- Branch-specific trigger inclusion was added to existing Android build/UI, Web and server CI workflows without changing their security permissions.
- Added cutover runbook, external blockers list, release readiness matrix and progress checkpoint.
- Fixed a stale 3.4-only Android updater UI fixture exposed after the version bump.

## Roadmap counts

Numbered roadmap status counts before → this checkpoint:

| ✅ | 🟡 | ⏳ | 🔌 |
|---:|---:|---:|---:|
| 71 → 72 | 35 → 34 | 8 → 8 | 12 → 12 |

Only roadmap item 52 changed, after its workbook and HTTP/Documents integration tests passed. TalAnt items 106–117 remain 🔌.

## Changed files and modules

- `.github/workflows/android-build.yml`, `.github/workflows/android-ui-tests.yml`, `.github/workflows/server-tests.yml`, `.github/workflows/web-tests.yml`
- `android_src/release.properties`, `android_src/tests/ui.test.cjs`
- `server/documents_api.py`, `server/production_service.py`, `server/report_xlsx.py`, `server/test_payroll_settlement.py`, new `server/test_report_xlsx.py`
- `PORTAL_MASTER_ROADMAP.md`
- `AGENTS.md`, `docs/PORTAL_KNOWLEDGE_BASE.md`, `docs/PORTAL_COMPANY_CONSTITUTION.md`
- `PORTAL_FINALIZATION_PART12_PROGRESS.md`, `PORTAL_FINAL_EXTERNAL_BLOCKERS.md`, `PORTAL_RELEASE_READINESS_MATRIX.md`, `PORTAL_PRODUCTION_CUTOVER_RUNBOOK.md`, `PORTAL_PART12_CHANGELOG.md`
- this report

## Local verification

- `python -m unittest discover -s server -p 'test_*.py' -v` — **206 total, 187 passed, 19 skipped, 0 failed**. Skips require isolated PostgreSQL/VPS or a local ReportLab runtime.
- `python -m unittest test_payroll_settlement test_report_xlsx test_production -v` — **53 passed, 0 failed**.
- `python -m unittest test_payroll_settlement.PayrollSettlementTest.test_payroll_xlsx_document_includes_settlement_sheet_and_payment_date -v` — **1 passed** (also included in the above suites).
- `python -m unittest test_report_xlsx -v` — **2 passed**.
- `node --test android_src/tests/ui.test.cjs` — **8 passed, 1 skipped locally** because Playwright is not installed in the local environment; GitHub Android UI run passed after the fixture fix.
- `node android_src/tests/build-security.test.cjs`, `employee-create-mode.test.cjs`, `native-shell.test.cjs`, `legacy-boundary.test.cjs`, `documents-chat.test.cjs` — all passed.
- `python -m compileall -q server android_src/tools`, targeted `node --check`, workflow YAML parse, and `git diff --check` — passed.

## GitHub Actions evidence

- SHA `0cec960`: Android build #29 ✅, server isolation #39 ✅, Web #11 ✅. Android UI #18 ❌ because an updater UI fixture still had a hard-coded 3.4 URL; fixed in `8408a33`.
- SHA `8408a33`: Android UI and Android build both ✅.
- SHA `f963649`: server isolation #40 ✅ and Web #12 ✅, covering the payroll export integration.
- SHA `fd51cc2`: Android build #31 ✅.
- SHA `0eb573e`: Android build #32 built successfully but artifact upload failed because the checksum-suffixed name was also used as a local file prefix. Fixed in `2b95dff`.
- Android UI run on `8408a33` ✅ after correcting the stale version fixture.
- Current staging build #33 on `2b95dff` ✅: [GitHub Actions run](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36636351641).
- Artifact: `PORTAL_Android_3.5-dev_staging_1804d3eaaeb95a87bd5424bf781f6cda767e1861bac004a43bba3126a884d054`; APK SHA-256 `1804d3eaaeb95a87bd5424bf781f6cda767e1861bac004a43bba3126a884d054`; artifact ZIP SHA-256 `dd98bfb5532ceb3e80a70a63e866f7f904bdfe4a1cd151c4c17f3d9fa6473e01`.

## VPS E2E and cleanup

- No Part 12 VPS or PostgreSQL E2E was run. No disposable PostgreSQL database/role or VPS temp resources were created by this checkpoint, so Part 12 cleanup counts are **not applicable (0 created)**.
- Parts 8–11 disposable PostgreSQL/Web E2E evidence remains in their respective reports; it is not represented as a new Part 12 run.
- No production DB, production service/configuration, production domain/DNS, signing secret, or real financial operation was used or changed.

## Security and release boundary

- Production cutover, final import, production migration, DNS switch, and release workflow: **NOT performed**.
- Physical phone/ADB was not used.
- APK is staging-only; it contains no first-login credentials or signing key material.
- Local Windows installer toolchain is unavailable (`dotnet` command is absent); no Windows installer was produced.

## Remaining software work (not external blockers)

- Complete invitation/access request APIs and Android/Web flows, company settings UI/enforcement matrix, and administrative audit UI.
- Complete client 360, tariff history UI, managed FBS/FBO/returns, normalization/rename history and product catalog UI.
- Complete payroll settlement UI, receivables aging, profitability and dashboard/productivity source-backed views, reminders/job runner, and cross-client Documents E2E.
- Complete Web Share browser behavior matrix and Windows thin client/installer/update strategy.
- Implement provider-neutral off-server backup automation, migration/cutover rehearsal tooling, full runtime `telegram_id` audit and legacy REAL money inventory/reconciliation.
- Run remaining broad security/role regression, VPS disposable PostgreSQL migration/rollback rehearsal, and final GitHub checks at the final implementation SHA.

## Manual owner checklist after a final staging candidate exists

1. Install the generated staging APK.
2. Log in and inspect primary role screens.
3. Open, save and share an Excel file.
4. Download a document.
5. Review the updater installer flow.

## Explicit production statement

**Production cutover was NOT performed.** This checkpoint does not mark Part 12 complete. Continue from `PORTAL_FINALIZATION_PART12_PROGRESS.md` and update this report only from verified evidence.

## Continuation №2 checkpoint — secure access/Audit slice

This is an in-progress local checkpoint based on `8460c71`; it does not claim A–D or Part 12 completion. No release or production action was taken.

### DONE NOW

- Added Stage 10 tenant-scoped invitation persistence and hash-only one-time token handling. Users are created inactive and require explicit approval. Expired/revoked/consumed token paths fail closed; PIN is sent only in the POST body. The login/PIN is never embedded in a URL.
- Added API and shared client flows for invite creation, existing/new employee selection, one-time safe copy/share, accept, list, approve and revoke. Added company active-seat summary and Platform Owner company fee/demo/status/limit editing; active-seat enforcement and concurrency lock use the existing server path.
- Added separate filtered/paginated company and owner audit views. Audit summaries omit credentials, raw tokens and arbitrary request payloads.
- Included the new PostgreSQL schema in disposable integration setup and the isolated Stage 7 migration list. This schema has FORCE RLS and append-only identity/status transition guards.

### TESTS RUN NOW

- `python -m unittest test_production -q` — **30 passed, 0 failed**.
- `python -m unittest test_portal_tenancy -q` — **15 passed, 0 failed**.
- `python -m unittest test_payroll_settlement test_report_xlsx -q` — **27 passed, 0 failed**.
- `node --test android_src/tests/ui.test.cjs android_src/tests/native-shell.test.cjs` — **9 passed, 1 skipped, 0 failed** (Playwright absent locally).
- `node --test android_src/tests/web-adapter.test.cjs android_src/tests/web-share.test.cjs` — **6 passed, 0 failed**. Adding `web-smoke.playwright.cjs` to a local run failed to load because Playwright is not installed locally; CI installs it.
- `node --check` (`app.js`, `production.js`, `ui.test.cjs`), `python -m compileall -q server`, `git diff --check` — passed.
- No disposable PostgreSQL/VPS test or cleanup ran. Android Gradle and GitHub CI for this new code remain pending.

### NOT DONE / NEXT

- This slice still needs commit/push and current-SHA CI. A’s browser role matrix and Stage 10 PostgreSQL RLS rehearsal have not run; the company-module toggle model was not found in the current schema and must be checked during continuation.
- Blocks B, C and D have not yet been implemented in this continuation. Do not promote roadmap statuses until their tests and E2E evidence exist.
- Parts 1–11 and previous Part 12 evidence remain tied to the SHAs and reports where they were tested; this section does not restate those runs as new.
- Production cutover **NOT performed**.

### GitHub results for `0006547`

- Server isolation #42: **success**.
- Web checks #15: **success**.
- Android UI #21: **success**.
- Android staging build #35: **success**; artifact `PORTAL_Android_3.5-dev_staging_78a5df419939da5c41e208018f52a809b93bed1a9e29eba4db320317974111ca`, APK SHA-256 `78a5df419939da5c41e208018f52a809b93bed1a9e29eba4db320317974111ca`, ZIP artifact digest `35fa5c07b9acb6113254d8b705ed140159246b0db624adaeab82a6654607d8ab`.
- These runs validate `0006547` only. PostgreSQL Stage 10 invitation/RLS and Documents two-session E2E were not run.

## Continuation №1 update — checkpoint `0770275`

This section supersedes the earlier report's “current HEAD” for the continuation work; earlier CI/APK evidence above remains attached only to the SHA where it ran.

### DONE NOW

- `490be25 test: cover same-company cross-session document sharing` adds an opt-in real PostgreSQL/HTTP E2E case using two independent auth sessions in one company. It tests create → list/metadata/download → archive → archive visibility across sessions. The fixture also retains cross-company denial tests. The new PostgreSQL case was skipped locally because this Windows environment has no WSL distribution or `psql`; it is not marked passed.
- `0770275 feat: add payroll settlement UI` adds balances/history and permission-gated payment and reversal actions to the shared client on top of the existing append-only, cents-based API. Payroll server ledger and migrations were not modified.

### TESTS AT THIS CHECKPOINT

- `python -m unittest test_documents_api test_portal_documents test_postgresql_documents_schema -q` (from `server/`): **21 passed, 0 failed**.
- `python -m unittest test_documents_postgresql -v` (from `server/`): **7 skipped**, all require opt-in disposable PostgreSQL.
- `python -m unittest test_payroll_settlement test_report_xlsx -q` (from `server/`): **27 passed, 0 failed**.
- `node --test android_src/tests/ui.test.cjs android_src/tests/documents-chat.test.cjs android_src/tests/documents-excel.test.cjs`: **17 passed, 1 skipped, 0 failed** (Playwright unavailable locally).
- `node --check android_src/app/src/main/assets/production.js`, `python -m compileall -q server`, `git diff --check`: passed.
- GitHub Actions runs for `490be25`: Web #13 (run `36638474846`) and Server #41 (run `36638474891`) were observed; Server #41 was still in progress at last observation. `0770275` has since been pushed and triggered new branch workflows; results remain to be read and recorded. `gh` CLI is unavailable.
- No Part 12 disposable PostgreSQL/VPS E2E or cleanup rehearsal occurred; no temporary DB/roles/files were created. Previous Parts 8–11 evidence is not represented as new Part 12 evidence.

### Roadmap reconciliation

No roadmap statuses changed on this continuation checkpoint. Item 38 stays 🟡 pending actual UI role-flow and integration validation. Items 53/55/56/68 stay 🟡 pending running the new disposable PostgreSQL cross-session test and the remaining UI parity work. Current numbered status counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**, unchanged from the previous report checkpoint.

### NEXT — software work remains

- Finish Blocks A–D as specified in the continuation task. Highest-priority immediate work: invitation/access lifecycle and company audit/settings; then B client/tariff/product/batch workflows; then finance aging/profitability/dashboard/reminders; then run Documents two-session E2E and finish parity/share tests.
- Run all four required latest-SHA GitHub gates (Server, Web, Android UI, Android staging build) and fix software failures.
- Use an available isolated disposable PostgreSQL runner for the new cross-session E2E and migration/rollback tests; no production DB/service may be touched.

**Security boundary:** Production DB/service/configuration, domain/DNS, signing secrets and physical phone were untouched. Production import/cutover **NOT performed**. This is an in-progress checkpoint, not final readiness or completion.

## Continuation №2 delta — tested code SHA `b6b4092`; current docs checkpoint `a4b6052`

Commits after the prior checkpoint: `0d477bf` tariff history query/view, `9bf3769` partial Client 360/tariff view, `26e595d` receivables aging API/UI, `b6b4092` invitation UI role-flow coverage. The `9bf3769` Android UI failure was caused by a Client 360 test fixture lacking the required client capabilities; the fixture now grants them and the browser suite passes.

### DONE NOW

- Receivables aging returns server-calculated integer-kopeck outstanding/overdue totals, aging buckets, per-client totals and paged invoice details; partial payments are counted once. Shared UI supports client and bucket filters.
- Tariff history is queryable and displayed as current/historical versions, with a warning that new rates do not recalculate prior work. Client 360 has permission-aware source-backed sections and an honest unavailable economics state.
- Browser coverage checks one-time invite token display, verifies PIN is not submitted in a URL, and confirms a manager without `users.manage` cannot reach invite controls/API.

### TESTS AT THIS CHECKPOINT

- Full server discovery: **212 passed, 20 skipped, 0 failed**. Skips need opt-in isolated PostgreSQL/VPS infrastructure; no DB resources were created in this run.
- Receivables aging boundary/partial-payment/cents/pagination test: **1/1 passed**.
- Playwright `ui.test.cjs`: **19 passed, 0 skipped, 0 failed**. UI + Web Share suite at `26e595d`: **21 passed**.
- JS syntax and `git diff --check`: passed.
- GitHub `26e595d`: Server #45, Web #19, Android UI #25 and APK build #39 all success. GitHub `b6b4092`: Android UI #26 and APK build #40 success. `b6b4092` changed only UI tests, so no Server workflow ran; local full server suite passed at that SHA.
- Staging metadata remains **3.5-dev-staging / versionCode 35**. APK SHA was not downloaded or recalculated in this continuation.
- Real Part 12 disposable PostgreSQL E2E and cleanup proof: **not run**; the existing Documents two-session E2E remains unexecuted.

### NOT DONE / NEXT

- A: full invite accept/approve/revoke and owner-selection role matrix; owner-audit filters and PostgreSQL RLS rehearsal; confirm settings/module-toggle support in the current data model.
- B: complete editable Client 360, tariff conflict and historical-work proofs, product CRUD/archive/search, aliases/rename history, batch plan/fact, idempotent FBS/FBO/returns.
- C: canonical profitability, dashboard/productivity source audit, reminder scheduler and broader payroll settlement role/integration tests.
- D: full Documents filters/history/grouping parity and actual disposable PostgreSQL two-session create/list/download/archive/cross-company denial run; rerun Android file contracts and Excel regression at final SHA.
- Roadmap counts unchanged: **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No status was promoted from these local or mocked UI tests.

**Production cutover NOT performed.** Production DB/service/configuration, DNS, financial operations, signing secrets and physical device were untouched.

## Automatic continuation update — tested code SHA `aa5cc64`

### DONE NOW

- Company audit view now offers actor, action, entity and date filters, with browser coverage confirming all query parameters are sent. This closes a UI filtering increment only; owner-audit authorization and PostgreSQL audit/RLS evidence are still pending.
- Shared payroll settlement UI now has a Playwright role-flow: an authorized admin adds a payment, sees paid/balance refresh while prior ledger history stays visible; a Manager with read-only settlement capability cannot write a payment.
- Web Share automated coverage now exercises the supported share path, user cancellation, unsupported capability fallback, object URL revocation, and file name/MIME allowlist.

### TESTS / COUNTS

- `node --test android_src/tests/ui.test.cjs`: **20 pass / 0 fail / 0 skip** at `aa5cc64`.
- `node --test android_src/tests/documents-excel.test.cjs`: **8 pass / 0 fail / 0 skip** at `320b6d9`.
- `node --test android_src/tests/web-share.test.cjs`: **5 pass / 0 fail / 0 skip** at `6137328`.
- From `server/`, `python -m unittest test_payroll_settlement -v`: **25 pass / 0 fail / 0 skip**, including workbook payment sheet and immutable snapshot coverage. Invoking that module from repository root initially failed module discovery; rerunning with the documented module directory passed.
- Relevant JS syntax checks and `git diff --check`: passed. No migration or server implementation changed in this continuation.
- GitHub runs for `6137328`: Web checks, Android UI, APK build all success. `aa5cc64` Android UI and APK build both succeeded; its Web workflow was not triggered for UI-test-only changes. Latest server run remains green #45 at `26e595d`, with no server-source changes. `cec4536` Web/UI/APK all green.

### D / ISOLATION EVIDENCE

- The real disposable PostgreSQL Documents two-session test and backup/restore rehearsal did not run: this environment has no `psql`, no test DSN configured, and no PostgreSQL opt-in flag. Repository workflows do not expose an isolated VPS runner for dispatch. No disposable database, role or temporary test resource was created, and production remains untouched.
- No CI artifact was downloaded, so no new APK hash is claimed. Staging metadata remains `3.5-dev-staging`, versionCode `35`.

### NOT DONE / NEXT

- Continue the real disposable PostgreSQL D test and cleanup proof when an isolated runner is available, while proceeding with C reminder framework/metrics and B/A software tasks.
- A–D remain incomplete; roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No completion or blocked flag was created.
- Current tested code SHA: `aa5cc64`; the follow-on docs checkpoint is source-only. Android UI/APK checks for the tested code SHA passed.

Production cutover **NOT performed**.

## Automatic continuation update — code SHA `5df9dc0` (full suite ran at parent `af29605`)

### DONE NOW

- Added a disabled-by-default reminder scheduling primitive with explicit company scope, daily/weekly cadence keyed to a caller-provided UTC offset, idempotency keys, duplicate detection, and retry after failed delivery. The `dispatch_once` callback contract requires the notification and unique key be persisted atomically in the caller's tenant-scoped transaction. The module itself does not query business data, send external messages, start a production timer, or persist results.
- Added five unit tests. `python -m unittest test_reminder_jobs -v`: **5 passed, 0 failed** at both `af29605` and the atomic callback follow-up `5df9dc0`.
- Commits `af296054d61f8a08fa4f109bc050a8693a8c417b` and `5df9dc0ec52abc6245bf642b7ddad7c607094849` pushed to `codex-finalization-megapack-part12`.

### REGRESSION / CI

- Full server discovery at `af29605`: `python -m unittest discover -s . -p "test*.py" -q` — **218 passed, 20 skipped, 0 failed** (177.014 seconds). Skips are opt-in PostgreSQL/VPS gates; this run created no disposable DB/role. At `5df9dc0`, the changed reminder module's targeted tests and compile checks passed; full server discovery was not rerun after this small callback-contract change.
- `python -m compileall -q reminder_jobs.py test_reminder_jobs.py` and `git diff --check` passed.
- Full Node `*.test.cjs` suite on `5df9dc0`: **42 passed, 0 failed, 0 skipped**, including browser Playwright and invitation/payroll/Documents/Excel/Web Share flows.
- GitHub Server Isolation run **#49 / 36649752281** and Web run **#26 / 36649752347** at `5df9dc0` both succeeded. Server matrix jobs on Python 3.11 and 3.13 each ran **218 tests, 19 skipped, 0 failed**. Android source did not change; latest successful Android UI/APK run remains `c09e44a`.
- Staging APK was not rebuilt for this backend-only commit. Previously verified artifact remains version `3.5-dev-staging` / versionCode `35`, APK SHA-256 `73596aedbcf1cec9145df112478acced79f48a07150142eae1bdbe042d7cae35`.

### NOT DONE / EXACT NEXT

- Reminder roadmap item 47 remains ⏳. Add real source-backed selectors for overdue invoices/unbilled work, tenant-persistent attention/run state and operator timer wiring; then test persistence, retries and duplicate suppression end to end.
- Run the real Documents independent-session E2E plus invite/RLS and settlement integration tests on disposable PostgreSQL and prove disposable DB/role/temp cleanup. Current environment has no `psql`, DSN or available isolated runner; production resources were not used.
- Continue remaining A/B/C/D software gaps listed in the progress checkpoint. Roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**; no status was promoted by this primitive.
- No completion/blocked flag created. Production DB/service/configuration, DNS, signing secrets, real financial operations and phone were untouched. Production cutover **NOT performed**.

## Platform Owner audit UI follow-up — SHA `1f3adc5`

- Added Playwright coverage for the separate owner audit view and filters; `node --test android_src/tests/ui.test.cjs`: **22 passed, 0 failed, 0 skipped**.
- GitHub Android UI workflow **#34 / 36650177640** and staging APK workflow **#48 / 36650177613** passed at this SHA.
- Artifact `PORTAL_Android_3.5-dev_staging_a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; APK SHA-256 `a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; ZIP digest `sha256:cdae0e6c93bbe0d714c73a4f41e2fd910c7819bb9a75906073a367e00d0b38c8`. Metadata remains 3.5-dev-staging / versionCode 35 / build 3.5.
- Server #49 and Web #26 passed at parent SHA `5df9dc0`; this follow-up changes browser tests only. Owner audit PostgreSQL/RLS and broader access policy tests remain open.

### Broader regression and source audit at code SHA `aa5cc64`

- Full server unittest discovery: **212 pass / 0 fail / 20 skip**. All skips are opt-in integration gates; no disposable database or role was created by this run.
- All Node `*.test.cjs` files: **41 pass / 0 fail / 0 skip**. Web adapter/share/smoke set: **9 pass / 0 fail / 0 skip**.
- `python -m compileall -q server ops`, parse of all **5** workflow YAML files, relevant JavaScript syntax checks and `git diff --check`: passed.
- Read-only identity audit: legacy server endpoints in `server/portal_app_server.py` still use `telegram_id` for employee linkage, assignments, work and payroll compatibility. Stage 3 uses canonical `employee_id` where available but still has a compatibility fallback; roadmap item 102 remains 🟡 and historic columns remain intentionally intact.
- Read-only money audit: settlement/receivables paths use integer minor units, while legacy endpoint calculations still convert money/quantity/stock values to `float`. A complete live SQLite `REAL` column inventory and reconciliation migration have not been performed; roadmap item 105 remains 🟡.
- Exact next software block is the disabled-by-default internal reminder runner with idempotency/cadence/retry/time tests, followed by remaining B product/name/batch workflows and A invite approval/settings/owner audit checks. The D real disposable PostgreSQL test remains unexecuted because this environment has no PostgreSQL client, DSN, opt-in flag, or repository-provided VPS runner.
- The audit does not change the **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌** roadmap counts. Production cutover **NOT performed**.

### Block A test addition — SHA `2ca0ad0`

- Added company-audit API integration assertions for actor/action/entity/date selection, safe summaries without PIN/token strings, pagination, descending chronology, and denial of packer and forged company-scope requests.
- `python -m unittest test_production -v` from `server/`: **32 pass / 0 fail / 0 skip**, including the new test. Full server discovery immediately before this test-only addition was **212 pass / 0 fail / 20 skip**.
- GitHub server-isolation and Web checks for `2ca0ad0` were in progress at the last poll; Android files did not change. Check the final workflow state before reporting a green SHA.
- No roadmap status changed. Audit item 15 remains 🟡 until owner-audit policy and PostgreSQL/RLS integration are proven.

## Automatic continuation update — current code checkpoint `aa94fa3`

- `e85078e` completes a limited Documents UI parity increment: virtual grouping by available company/client/employee, category, type and month metadata, with current/archive labels. Browser tests verify folders and document states; this is not evidence of cross-client server synchronization.
- Integrated `1066c77` as `05ab65e`. `aa94fa3` adds two safety corrections: do not print arbitrary SQL validation output during restore rehearsal; reject unsafe backup filename prefixes used for retention pruning.
- `ops.test_infra_readiness`: **7/7 passed**; `compileall ops`, UI Playwright **19/19**, Documents/Excel/chat/Web Share contracts **12/12**, syntax and diff checks passed.
- GitHub UI SHA `e85078e`: Web #20, Android UI #27, APK #41 green. Server #45 at `26e595d` remains the latest server workflow; server code did not change in these UI/ops commits. Full server discovery at `b6b4092`: **212 passed, 20 skipped, 0 failed**.
- PostgreSQL backup/restore rehearsal and Documents cross-session E2E are **not run**; no isolated test DB/role was created. Only ops helper tests used temporary local files/mocked subprocess results. External backup target remains unconfigured; production untouched.
- Roadmap remains **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**; no status promotions.

### Exact NEXT

Continue C source-backed profitability, productivity/radar and disabled-by-default reminders with idempotency/cadence/retry/time tests. Then finish D real disposable PostgreSQL Documents cross-session E2E and Android/Web file parity; continue B product/batch/returns/name-history and A approval/settings/audit role matrix. Follow with disposable PG backup restore, legacy money/identity audits, Windows thin client/news framework, then full final regression and GitHub CI. Do not create a completion or blocked flag until the corresponding condition is true.

## Automatic continuation checkpoint — `da28db0`

### DONE NOW

- `854520f` adds a real PostgreSQL-backed Stage 10 invitation lifecycle/API integration test; `da28db0` adds denial for a separately authenticated packer without `users.manage`.
- The test proves hash-at-rest and one-time/idempotent behavior; successful accept, approval and login; consumed-token denial; cross-company list/accept isolation; forged company-header rejection; and audit summaries that do not contain the raw token.
- Both commits are pushed on `codex-finalization-megapack-part12`. No schema change was required.

### TESTS / CI

- Three targeted SQLite/API lifecycle tests: **3 passed**. Full `python -m unittest test_production -v`: **32 passed, 0 failed**.
- Local PostgreSQL suite invocation: **8 skipped** because no local PostgreSQL client/DSN/integration gate is configured. The real isolated GitHub run is the evidence: Web **#33 / 36651996603** at `da28db0`, with both Web and PostgreSQL jobs successful. The PostgreSQL job ran all eight fixture tests: **6 passed, 2 skipped** (real PDF and in-fixture browser-only gates).
- GitHub Server **#55 / 36651996627** at `da28db0`: Python 3.11 and 3.13 both successful. The predecessor Web run **#32 / 36651817020** also succeeded at `854520f`.
- Disposable PostgreSQL fixture cleanup verified DB=0, roles=0, temp=0. The fixture uses loopback-only `postgres` admin in a temporary PostgreSQL 16 service, random `portal_test_*` database and restricted `NOSUPERUSER NOBYPASSRLS` application roles. Production DB/service/configuration were untouched.
- `python -m compileall -q server`, `git diff --check` passed. No Android code changed; staging remains **3.5-dev-staging / versionCode 35**. The newest previously built artifact is unchanged and is not rebuilt for this backend test-only continuation.

### ROADMAP

- Counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. Items 10–12 and 15 stay 🟡 because remaining owner/settings policy and complete role matrix are not proven. Documents same-company cross-session synchronization and invitation tenant isolation now have current Part 12 disposable PostgreSQL evidence, but broader parity and release/production gates remain open.

### NOT DONE / EXACT NEXT

- A: owner/director settings policy (including explicit module-toggle support review), owner-audit PostgreSQL authorization, and expanded employee/invitation role flows.
- B: product CRUD/archive/search, stable-ID alias/rename history, batch economics completeness and generic FBS/FBO/returns lifecycle.
- C: persistent reminder candidate/dispatch path, canonical profitability/productivity/radar and payroll settlement PostgreSQL role coverage.
- D: complete shared Documents UI parity and Web Share/Android file contracts. The real same-company Documents HTTP/PostgreSQL scenario passed in run #33; do not repeat it as unrun.
- Exact next: proceed with A owner/director settings and owner audit policy, test server enforcement and UI role matrix, then continue B/C. Full regression, legacy identity/money work and remaining external readiness still follow. Production cutover **NOT performed**; no completion/blocked flag created.

A–D and Part 12 are **not complete**. No production cutover was performed.

## Automatic continuation №2 — code SHA `d853677`

### DONE NOW

- PostgreSQL Stage 10 invitation coverage from `854520f`/`da28db0` remains green.
- `d31d760` corrects a test-only Python method-binding error in the disposable PostgreSQL fixture.
- `d853677` validates the default 15-active-user limit, server rejection of a new active user at capacity, unchanged active count, and forged company-scope denial. The same isolated suite validates Platform Owner audit login filtering and denies company admin/packer access.
- No product schema or production configuration was changed in this increment.

### TESTS / CI

- Local targeted A regression: **4 passed**; local PostgreSQL invocation: **10 skipped** because local PostgreSQL is not configured.
- Web #39 / `36653710143`: Web and disposable PostgreSQL jobs succeeded at `d853677`. PostgreSQL: **10 tests, 8 passed, 2 skipped** (real PDF/browser-only gates); cleanup: **database=0, roles=0, temp=0**.
- Server #61 / `36653710121`: Python 3.11 and 3.13 each ran **221 tests, 22 skipped, 0 failed**.
- The failed Web attempts #34–#37 were caused by the newly added test calling `make_conninfo` as a bound instance method. The call now goes through `type(self)` and both owner-audit and active-limit tests pass on Web #39. No authorization or security gate was weakened.
- `python -m compileall -q .` from `server/` and `git diff --check` passed. Android/Node source did not change; 3.5-dev-staging / versionCode 35 remains unchanged.

### ROADMAP / NEXT

- Counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. A items 10–12/15 remain 🟡 pending the full role matrix, missing company module-toggle model, director settings UI and production gates.
- Exact next: define additive module-toggle/settings storage and enforce it server-side; cover director-owned settings plus Platform Owner explicit company selection, then continue B product/client/batch workflows and C payroll/profitability/reminders. D UI/share parity and final Android checks remain after those.
- Production cutover **NOT performed**. No completion or blocked flag created; software work remains.

### Owner explicit-company invitation follow-up — `ea531c5`

- The disposable PostgreSQL owner test now covers both denial with no company selection and successful invitation creation after explicitly selecting company 2. It asserts the resulting invite belongs to company 2 and the one-time token is scoped to that company.
- GitHub Web **#40 / 36654066963**: Web and PostgreSQL jobs successful; PG suite **10 tests, 8 passed, 2 skipped**, cleanup verified DB=0/roles=0/temp=0. GitHub Server **#62 / 36654067004**: Python 3.11 and 3.13 each **221 tests, 22 skipped, 0 failed**.
- Targeted local invite role tests **2 passed**; local PG gate remains skipped because this workstation has no isolated PostgreSQL. `compileall` and `git diff --check` passed.
- Roadmap counts stay **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. Existing-employee flow matrix, module toggles/director settings UI, Blocks B/C/D remainder and final Android/Web release checks remain. Production cutover **NOT performed**.
# Automatic continuation addendum — 2026-09-30

## Current checkpoint

- Current code SHA: `042a6fb8e583a9325c307cdd779191c743ed2b56`; Server #67 and Web #45 are green.
- Commits in this continuation: `f2b39cc` (stable invoice document retry request ID), `d64f965` (disposable PostgreSQL payroll settlement role flow), `042a6fb` (PostgreSQL-native minor-unit type assertion).
- No application code, schema migration, Android source, release metadata, production service, or production database changed in these three commits; changes are test-only.

## Evidence added

- Server #66 at `f2b39cc`: Python 3.11 and 3.13 each ran 222 tests, with 23 skipped and 0 failures.
- Web #43 at `f2b39cc`: Web and PostgreSQL jobs passed; disposable fixture ran 11 tests, 2 skipped; cleanup reported DB=0, roles=0, temp=0.
- Web #45 at `042a6fb`: Web and PostgreSQL jobs passed; fixture ran 12 tests, 2 skipped; cleanup reported DB=0, roles=0, temp=0. The added HTTP/API test verifies authorized admin payout, packer and foreign-company denial, idempotent retry, exact minor-unit balance and unchanged closed payroll snapshot.
- Server #67 at `042a6fb`: Python 3.11 and 3.13 each ran **223 tests, 24 skipped, 0 failed**.
- Targeted local Documents/schema suite: 21 passed, 0 failed. Local server discovery/PG fixture did not create disposable resources. Compile and diff checks passed before pushes.
- Failures fixed during this continuation: Server #64 had an unstable test request ID; Web #44 used SQLite `typeof()` against PostgreSQL. Both were test-only corrections, and no gate or application authorization was weakened.

## Status and next

- Roadmap counts remain 72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌. Item 11 now notes that existing-employee invitation linking is verified on disposable PostgreSQL; broader role coverage remains open.
- A–D and Part 12 are not complete. Continue first with Server #67 outcome, then A settings/module policy, B catalog/aliases/batches/internal workflows, C persistent reminders/profitability/radar/productivity, and D remaining Documents parity and Android/Web file contracts. Update evidence again after relevant tests.
- Latest APK evidence remains the previously documented 3.5-dev-staging / versionCode 35 artifact at `1f3adc5`; it is not a build of the current SHA. No new APK was needed for these test-only commits.
- No autopilot flag was created. Production cutover **NOT performed**.

## Automatic continuation — product catalog / batch economics, 2026-09-30

Current tested code SHA: `4e38943cb8e9262e95701081f6ffc3f6ca5a7f5c`. Commits: `c5e75ec` stable client product catalog; `4e38943` unavailable-plan rendering and integer-kopeck per-unit rounding.

- Roadmap item 35 is ✅ after service tests, Playwright create/rename/archive/search, stable product-to-batch ID/snapshot behavior, and successful Stage 12 disposable PostgreSQL Web job. Counts changed from 72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌 to **73 ✅ / 33 🟡 / 8 ⏳ / 12 🔌**. No other item was promoted.
- Local server discovery: **228 passed, 27 skipped, 0 failed**. All Node tests: **46 passed, 0 skipped, 0 failed**. Focused browser UI: **25 passed**. Ops infra tests: **7 passed**. Compileall, Node syntax checks, workflow YAML parsing, and diff check passed.
- GitHub Server `36658950142`, Web `36658950177` including `documents-postgresql`, Android UI `36658950145`, and APK build `36658950150`: all success at the tested SHA. Artifact: `PORTAL_Android_3.5-dev_staging_7d0a6bf83b17054b9f53697c1fb69e77de90ebefa55c1ca2988a001548efed65`; APK SHA-256 `7d0a6bf83b17054b9f53697c1fb69e77de90ebefa55c1ca2988a001548efed65`; archive SHA-256 `f9a644f2b3fccafc88fd4fdf4ee000240390e3894dfd52e215222fe31dea8c67`.
- New Stage 12 migration is additive and edits only the product catalog metadata allowlist in the immutability trigger. Product/batch facts were tested on CI disposable PostgreSQL; local PostgreSQL was unavailable and no local disposable resources were created. No production mutation/cutover occurred.
- Remaining A–D software work: A director settings and remaining role matrix; B tariff conflict/history, client aliases/rename, batch economics completeness, FBS/FBO/returns; C persistent source-backed reminders, profitability/productivity/radar; D remaining Documents parity and platform file/share contract gaps. Exact NEXT: implement reminder candidates and tenant-persistent idempotent internal notifications for overdue invoices and unbilled completed work, with PostgreSQL tests; then continue B/A/D. Part 12 is not complete; no autopilot flag was created.
