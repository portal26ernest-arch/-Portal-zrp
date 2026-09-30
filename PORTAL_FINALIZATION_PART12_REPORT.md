# PORTAL Finalization Part 12 — checkpoint report

**Status: IN PROGRESS; Definition of Done is not met.** This report is an evidence checkpoint, not a claim that all Part 12 requirements are finished.

Дата: 2026-09-30
Verified Part 11 base: `bc95a942021bb5c43d112f51d2c2e7881059b47a`
Original bootstrap checkpoint implementation HEAD: `2b95dffe891d80244487bcc7fef9ce081acdc468` (superseded by the latest automatic continuation checkpoint below).
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

## Automatic continuation — reminder candidates and internal notification sink

Latest tested code at `e08e0d8dbe927cce9b82ab58e4ef4a5c7e9c29a4`; commits `cd22c20`, `2db871e`, `e08e0d8`.

- Source selectors derive overdue invoice candidates after payments (including partial payments) and unbilled completed work from the selected company's rows. The append-only notification sink uses atomic insert-once and appears in `PORTAL Сегодня` only for users with invoice/finance read capability.
- Local reminder tests: **7 passed**; combined reminder/dashboard tests: **8 passed**; server discovery: **232 passed, 28 skipped, 0 failed**. The local disposable PostgreSQL test class skipped **15 tests**, with no resources created. CI Web `36660208411` passed Web and disposable PostgreSQL; teardown verified DB=0, roles=0, temp=0. CI Server `36660208403` passed Python 3.11/3.13.
- Earlier Web disposable PostgreSQL runs `36659765933` and `36659903107` failed for the newly added scenario. Public run summaries did not expose test output beyond exit code 1; exact initial cause is unknown. The final PG test isolates insert-once, duplicate suppression, and tenant visibility; that run passed. No security gate was relaxed.
- Reminder scheduling remains incomplete: no operator timer, run metadata, or production enablement. Item 47 remains ⏳ and roadmap counts remain **73 ✅ / 33 🟡 / 8 ⏳ / 12 🔌**.
- Exact NEXT: add disabled-by-default operator cadence/run/retry persistence, then test retry and concurrent deduplication on disposable PostgreSQL. Continue remaining A/B/C/D gaps. Production cutover **NOT performed**; no autopilot completion/blocked flag.

## Continuation №3 — source-backed dashboard and tariff/date integrity

### DONE NOW

- Base checkpoint: `9c41aa856c6efdeb796f05694d7d3a6b71b76176`; final code SHA: `7917dacffaf1e0241595ccd63ab0336dbf43568a`. Logical commits: `b307c32` director dashboard/date metrics, `da4b493` PostgreSQL dashboard E2E, `635e692` tariff date/history tests, `2548d97` team productivity display, `7917dac` company-local finance month buckets.
- Dashboard uses server facts for day/month volume and financials, open/overdue invoice count and balance, active jobs and closed-period payouts. Plan profit is `null` and shown as unavailable when plan sources are absent. Team units/hour are computed only from completed work with valid duration; missing duration is clearly unavailable.
- Financial trend months use the company UTC offset for work, material usage and expense event dates.
- Tariff tests prove the old work snapshot remains unchanged, a future effective tariff is selected after its boundary, and duplicate effective timestamps are rejected.
- The Web fixture includes two disposable PostgreSQL tests for dashboard tenant isolation and effective-date tariff snapshots. Web #61 passed at `2548d97`; fixture setup uses a fresh `portal_test_web_*` DB and restricted `portal_web_*` roles and teardown fails unless DB/roles/temp resources are gone.

### TESTS AND CI

- Current local Server discovery at `7917dac`: **244 passed, 31 skipped, 0 failed**.
- Full Node test suite at `2548d97`: **47 passed, 0 skipped, 0 failed**; focused Playwright UI: **26 passed**. No Android/Node files changed after that run.
- Ops readiness tests: **7 passed**. Compileall, JS syntax, workflow YAML parse and `git diff --check` passed.
- GitHub at `2548d97`: Server #83, Web #61 including disposable PostgreSQL, Android UI #41, Android APK #55 — all success.
- GitHub at `7917dac`: Server #84 and Web #62 — both success. Android app source was unchanged after #41/#55.
- Staging artifact: `PORTAL_Android_3.5-dev_staging_481dc11b4d9fcb1bd6cbef87a29605feab42ac6fb72fbe1a8886f71f57502f74`; APK SHA-256 `481dc11b4d9fcb1bd6cbef87a29605feab42ac6fb72fbe1a8886f71f57502f74`; build remains `3.5-dev-staging`, versionCode 35.
- Local PostgreSQL fixture was skipped (no isolated local service/DSN) and created zero resources. GitHub disposable fixture passed; no production target was used. Earlier Parts 8–11 evidence is not counted as a new Part 12 run.

### ROADMAP / NOT DONE

- Numbered roadmap counts are **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**. Items 19 and 44–47 evidence text was refreshed. Item 47 moved from ⏳ to 🟡 after code/tests established the company-scoped disabled operator runner and persistent cadence/run/retry records; system timer/configuration remain missing.
- A–D remain incomplete. Next: continue source-backed profitability and remaining Client 360/alias/workflow gaps, then audit the unfinished role/settings and Documents parity paths. The reminder operator runner remains disabled-by-default and manually invoked; no production timer is enabled.
- Next wider software tasks: employee ID legacy boundary and money cents inventory/reconciliation, safe marketplace news operator framework, backup restore rehearsal, Windows installer/toolchain, then final full readiness evidence.
- Production cutover **NOT performed**. No autopilot completion or blocked flag created; software-completable work remains.

## Automatic continuation — client aliases and shipment lifecycle (`e85928e`)

- `056e1e8` adds Knowledge Base spelling aliases to Client search while preserving stable client IDs and canonical names.
- `e85928e` adds service, disposable PostgreSQL HTTP, and Playwright coverage for idempotent FBS/FBO shipment completion, audit, single-row shipment history, request-key conflict rejection, and tenant/role denial.
- Local evidence: Server discovery **249 passed / 34 skipped / 0 failed**; Node suite **49 passed / 0 skipped / 0 failed**; focused browser UI **28 passed**; shipment service test **1 passed**; infrastructure readiness **7 passed**; compileall, relevant `node --check`, and `git diff --check` passed. The isolated PostgreSQL test skipped locally because no disposable DSN is configured.
- GitHub at `056e1e8`: Web #75 + disposable PostgreSQL, Android UI #48, and APK #62 passed. Staging artifact `PORTAL_Android_3.5-dev_staging_d5c65948ad3a2909eb394c1330fab23d66efa48cbe51236ad3715cbcd7ad7e2d`; APK SHA-256 is the 64-hex suffix.
- GitHub at `e85928e`: Web #76 + disposable PostgreSQL, Android UI #49, APK #63, and Server #93 (Python 3.11/3.13) passed. Staging artifact `PORTAL_Android_3.5-dev_staging_daf9604d76bdf2f4bea40b065302ae6020371da6f49e8a74676b575b7aee7839`; APK SHA-256 is the 64-hex suffix. The isolated PostgreSQL fixture asserts DB=0, roles=0, temp=0 at teardown. Version remains 3.5-dev-staging/versionCode 35.
- Item 32 is now ✅ from the internal workflow evidence; counts are **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Production DB/service, DNS, financial facts, signing secrets, and physical device were not used. Production cutover **NOT performed**.
- Exact NEXT: continue A invite/audit/settings role completeness, B Client 360 editability, C unified profitability/reminder configuration, and D document revision-history parity. Then complete legacy ID/money audits, news framework, backup rehearsal, Windows installer and final integration checks. No completion/blocked flag while software work remains.

## Automatic continuation — company control settings and latest integration check

- Latest checked branch HEAD: `2a0ab8f570de3a79ce6513df334ed284c1384b42` (`test: cover company control settings authorization`), following `ae9f83f` and `50a9e3e`. The shared Settings screen now exposes existing company control settings only to users with `company.settings`; the browser verifies a Director can read/save without submitting a company ID and a Manager cannot see the link. Server test verifies Director allow, Manager deny, and forged company header deny.
- Tests at this checkpoint: full server discovery **246 passed / 33 skipped / 0 failed**; full Node/Android suite **48 passed / 0 skipped / 0 failed**; targeted browser UI **27/27**; infrastructure readiness **7/7**; compileall, JS syntax and diff checks passed.
- CI: Server `36667262958` and Web `36667263031` passed at `2a0ab8f`; Android UI `36667166698` and Android APK `36667166789` passed at `50a9e3e` (the later `2a0ab8f` changes only server tests). Staging remains 3.5-dev-staging/versionCode 35. APK artifact `PORTAL_Android_3.5-dev_staging_d34c2d8fd3714ffa6deae9ae6cec26e46879937d6d5b09bfe7e30d330301fdd4`, SHA-256 `d34c2d8fd3714ffa6deae9ae6cec26e46879937d6d5b09bfe7e30d330301fdd4`.
- Roadmap item 12 remains 🟡 and counts stay **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**. This UI completes discoverability of the existing control settings, not every allowed company preference. No production DB/service, DNS, financial facts, credentials, signing keys, or phone were used; production cutover **NOT performed**.
- Exact NEXT: continue the outstanding invitation/audit policy paths, Client 360/normalization and batch workflow gaps, canonical profitability and reminder cadence, and Documents UI parity. Then complete employee ID/money inventories and remaining release-readiness work. No completion/blocked flag is justified while software work remains.

## Automatic continuation — Documents filter parity and integration regression

- At `3223ad0`, Documents UI added permission-aware client and employee ID filters using existing server query parameters. Browser verified authorized request construction and absence of both fields for `documents.read`-only user; `ba9035a` added canonical stable employee-ID query and forged company scope denial. Test-only correction `c732067` reuses payroll XLSX request ID on retry.
- Current code/test branch SHA `c7320674f4cd033f4e60ad16a7286cae7a69596a`. Server suite: GitHub Server `36668180785`, Python 3.11/3.13 each **247 tests, 32 skipped, 0 failures**. Targeted Documents APIs/schema: **22/22**. Full Node/Android suite at UI code SHA: **48/48**.
- GitHub Web `36668181017`: disposable PostgreSQL **20 tests / 18 pass / 2 skipped**, including independent same-company sessions and cross-company denial; cleanup `DB=0 roles=0 temp=0`. GitHub Android UI `36667824748` and APK `36667824984` passed at `3223ad0`. Staging 3.5-dev-staging/versionCode 35; artifact suffix/SHA-256 `d9a8def27b9365eda12d419aefcd95f40831d31715e56626577e6391116f57a5`.
- An earlier Server run `36667911551` failed on a test retry that generated a new request ID; the assertion was corrected by reusing the same key, and repeat suite/CI at `c732067` passed. No application security or idempotency behavior was weakened.
- Roadmap stays **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**. Production cutover **NOT performed**. Exact NEXT: continue A invitation/audit/settings role coverage, B Client 360/normalization/batches, C profitability/productivity/reminder cadence, D history parity, then legacy ID/money audits and final release gates. Software work remains, so do not create completion/blocked flag.

## AUTOMATIC CONTINUATION — Client 360 requisites and productivity period comparison — 2026-09-30

### DONE NOW

- Continued from actual pushed branch state `a4dd960`; kept the existing Part 12 worktree and branch.
- `819dbfb` completed the first editable Client 360 requisite block using existing `portal_client_requisites`. Server reads/writes enforce current company/client visibility and `clients.read`/`clients.manage`; idempotent request retries return the original result. Audit records a safe action and client identity only, never the field values. Shared Android/Web UI permits edits only to `clients.manage` and reloads canonical values after save.
- Added a disposable PostgreSQL API/RLS integration scenario to the existing Web gate. The test checks same-company independent-session visibility, company B isolation, forged header denial, retry idempotency, and absence of tax/bank values from audit. Locally it is skipped because this environment does not provide the disposable test PostgreSQL service.
- `f5475ae` completed one productivity comparison block: optional date range vs an immediately prior equal-length period, interpreted with company-local offset. Quantity and delta use actual work records; hourly pace uses only valid timed work; no timing produces an unavailable result. UI date filters show both exact date windows.
- The numbered roadmap count is unchanged at **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Items 17 and 46 remain 🟡 because broader Client 360 and productivity acceptance remains.

### TESTS RUN NOW

- Requisites server test: **1 passed**. Full server discovery after both code blocks: **254 passed, 36 skipped, 0 failed**.
- Browser UI after both blocks: **29 passed, 0 skipped, 0 failed**. Full Node suite: **50 passed, 0 skipped, 0 failed**.
- Analytics period API test: **1 passed**. Infrastructure readiness: **7 passed**. `python -m compileall -q server ops android_src/tools`, relevant `node --check`, and `git diff --check`: passed.
- At `819dbfb`, GitHub Server/Web/Android UI/Android APK (`36677295945`, `36677295988`, `36677295987`, `36677295995`) all succeeded. At `f5475ae`, Web #`36678086685`, its `documents-postgresql` job, Android UI #`36678086723`, and APK #`36678086692` succeeded; Server #`36678086835` was still in progress when recorded.
- Staging artifact at `f5475ae`: `PORTAL_Android_3.5-dev_staging_67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`; APK SHA-256 is the 64-hex suffix. Version remains 3.5-dev-staging/versionCode 35.
- No disposable database, role or temp resource was created locally; the Web CI disposable test performs teardown assertions. No production DB/service, DNS, financial data, credentials, signing secrets or physical phone was used. No production cutover.

### PREVIOUSLY PROVEN

- Earlier Part 12 evidence remains as described in preceding checkpoint sections; it is not presented as a new run for this continuation.
- Existing assistant infrastructure commit `1066c77` was already integrated and its seven infrastructure tests had passed on an earlier checkpoint; this turn reran `ops.test_infra_readiness` **7/7**.

### NOT DONE / EXACT NEXT

- A invitation/access/settings/audit policy matrix remains incomplete.
- B Client 360 still needs the remaining linked/editable blocks and normalization/history acceptance; item 17 stays 🟡.
- C still needs broader profitability/reconciliation and reminder cadence/operator execution; production timer remains disabled.
- D still needs successful execution of the new requisites PostgreSQL test in Web CI, remaining document revision/history parity and final Android/Web file contracts.
- Exact next: poll the four workflows on `f5475ae`; diagnose any failure, then continue A authorization coverage or C reminder cadence/source-backed profit. After CI is green, refresh these checkpoints with run IDs, then commit/push the docs checkpoint.
- Broader remaining work: employee ID/legacy telegram ID runtime audit, REAL money inventory and additive cents reconciliation strategy, disabled news operator framework, disposable backup restore rehearsal, Windows thin client/installer, and final full regression. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — Client 360 Documents drilldown — 2026-09-30

### DONE NOW

- `b588462` adds a Client 360 action to open the shared Documents screen filtered to that stable client ID, using the existing server `client_id` query filter and document/client capabilities. Browser tests assert the canonical request and active client filter.
- UI browser tests: **29 passed, 0 failed**. Full Android/Node tests: **50 passed, 0 failed**. `node --check` for the changed JavaScript files and `git diff --check` passed.
- On parent SHA `f5475ae`, Server `36678086835`, Web `36678086685`, Android UI `36678086723`, and Android APK `36678086692` all succeeded. The Web disposable PostgreSQL job passed. Staging artifact: `PORTAL_Android_3.5-dev_staging_67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`; SHA-256 `67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`; staging remains 3.5-dev-staging/versionCode 35.
- Roadmap count remains **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; A–D remain incomplete. No production systems were touched.

### PREVIOUSLY PROVEN

- `819dbfb` Client 360 requisite API/UI; `f5475ae` productivity comparison. Earlier PG and full server results apply to those named SHAs only.
- Documents cross-session PG E2E passed in Web CI at `f5475ae`; it is not claimed as a new `b588462` run.

### NOT DONE / EXACT NEXT

- A: invitation/access/settings/audit role-policy coverage remains partial.
- B: more source-backed editable/linked Client 360 sections and broader normalization/history proof remain.
- C: profitability/reconciliation breadth and reminder cadence/operator run remain; production scheduler remains disabled.
- D: revision/history UI parity and final share/file contracts remain; rerun disposable PG cross-session E2E at the final code SHA.
- Exact next: poll Server/Web/Android UI/Android APK for `b588462`; fix any software failure, then continue A role coverage or C reminder cadence with tests and a logical commit. Counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Production cutover **NOT performed**.

### Integration regression follow-up

- Server unittest discovery: **254 run, 36 skipped, 0 failures** at `967e947` (server source matches `f5475ae`). An initial run concurrent with infra checks had one non-reproducible invoice-document idempotency assertion; its target passed independently, then full suite passed on isolated rerun. Contract/test limits were not relaxed.
- Infra readiness: **7/7 passed**; Python compileall passed.
- At source ancestor `b588462`, Web #`36678773323`, Android UI #`36678773573`, and APK #`36678773473` passed. Server #`36678086835` passed at `f5475ae` with unchanged server code. Web disposable PostgreSQL documents job #`36678086685` passed at `f5475ae`. `967e947` is a documentation-only descendant; no source changed.

## AUTOMATIC CONTINUATION — Client 360 receivables drilldown — 2026-09-30

### DONE NOW

- `64dc650` opens existing receivables aging from Client 360 with `client_id`, resets local filters/page, and enforces `invoices.read`. Browser test covers the authorized filter and permission denial. No new server calculations or synthetic balances.
- Browser UI **29 passed**, full Node/Android **50 passed**, JS syntax checks and `git diff --check` passed.
- `b588462` Web/Android UI/APK workflows are green. For `64dc650`, Web #`36680058456`, Android UI #`36680058499`, APK #`36680058649` were in progress. Server source is unchanged since green Server #`36678086835` at `f5475ae`.
- Roadmap counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Production cutover not performed.

### NOT DONE / EXACT NEXT

- A–D remain partial: invitation/settings/audit role completeness; other Client 360 editable links/normalization; more source-backed profit and reminder cadence; final document history/role parity and disposable PG proof on current code.
- Exact next: poll `64dc650` Web/Android UI/APK plus its PostgreSQL job; fix any software failure. Then continue A role matrix or C reminder/operator coverage, test, commit and push. No completion/blocked flag is warranted while software work remains.

### GitHub CI finalization for this checkpoint

- At code SHA `64dc650f5818d891d27e95e99c1d471f6e50923e`: Web #`36680058456` (with `documents-postgresql`), Android UI #`36680058499`, and Android APK #`36680058649` succeeded.
- Server workflow was not triggered because server source did not change; same server code passed Server #`36678086835` at `f5475ae`, and local discovery at current source was **254 passed, 36 skipped**.
- Anonymous GitHub API returned 403 for job logs, so no new DB/role/temp cleanup counts are claimed from this run. Earlier fixture cleanup evidence remains attributed to its earlier SHA/run.
- No build version change: staging remains 3.5-dev-staging/versionCode 35.

## AUTOMATIC CONTINUATION REPORT — invitation role and audit evidence — 2026-09-30

### DONE NOW

- `510becd` emits company audit events for settings and capability changes with field names only; values are excluded. `bd8222b` restores mutable PostgreSQL settings/capability test fixtures.
- `6c6c4ee` adds cross-role and tenant invitation decision assertions: Director approve, Manager/Packer denial, cross-company rejection, forged header rejection, one-time approval audit, idempotent Director revoke, and rejection of a revoked token.
- Readiness counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; no roadmap status was promoted by this incremental coverage.

### PREVIOUSLY PROVEN

- Prior Documents independent-session PostgreSQL E2E and cleanup evidence remain attributed to the named earlier Web run in the readiness matrix; this continuation does not present it as a new run.
- `1066c77` infrastructure-readiness work was already integrated. This continuation reran `ops.test_infra_readiness` successfully.

### TESTS / CI

- Local targeted invite role test: **1 passed**. Full server unittest discovery: **258 tests, 39 skipped, 0 failed**. Local opt-in PostgreSQL module: **26 skipped** because no disposable local PostgreSQL configuration is present. Compileall, infra tests **7/7**, and `git diff --check` passed.
- Web CI #`36682830228`: both `documents-postgresql` and `web` jobs passed at `6c6c4ee`. Server CI #`36682830272`: Python 3.11 and 3.13 jobs passed.
- The preceding Web job at `229650a` failed due to a response-shape assumption in the new test; it was corrected and rerun green at `6c6c4ee`. `bd8222b` Web #`36681705904` and Server #`36681705913` were green for the settings/audit fixture changes.
- Staging remains 3.5-dev-staging/versionCode 35. Server-only tests did not require a new APK. No production resources were changed.

### NOT DONE / EXACT NEXT

- A–D still have software work remaining: owner/director settings/audit coverage; Client 360/batch/normalization cases; unified source-backed profitability and persistent reminder cadence; document history/revision parity and final disposable PostgreSQL run.
- Next code task: add focused shared UI regression for document history revision ordering and permission-aware access, then continue remaining blocks. Employee-ID/legacy Telegram-ID runtime audit, REAL-money inventory, news operator framework, backup restore rehearsal, Windows thin client, and final integrated regression remain. No autopilot flag and no production cutover.

## AUTOMATIC CONTINUATION REPORT — settings and owner audit role evidence — 2026-09-30

### DONE NOW

- `166fa35` corrects test request construction for same-company director settings; it includes explicit idempotency identifiers in the role-denial HTTP assertions.
- `dde82b0` verifies Platform Owner audit filters for company, actor, event, date and pagination against disposable PostgreSQL. The same request also asserts company-user and packer denial and excludes the synthetic PIN from the response.
- Confirmed that shared Documents UI and PostgreSQL tests already cover revision order, archived/current labels, read-only history, unauthorized-access denial, same-company cross-session visibility and archive consistency. This was existing code/test evidence, not new implementation in this turn.

### PREVIOUSLY PROVEN

- At `166fa35`, Server #111 and Web #97 were green. Web #97 included successful `documents-postgresql`; reminder settings default-off/cadence tests ran in that disposable job.
- At `dde82b0`, Web #98 / run `36688962524` passed, including the new disposable PostgreSQL owner-audit filters and existing Documents history tests.
- Staging remains 3.5-dev-staging/versionCode 35. No production resources were touched.

### TESTS

- Local `test_production`: **45 passed**; local `test_portal_tenancy`: **16 passed**; full server discovery at `dde82b0`: **259 passed, 39 skipped, 0 failed**; browser UI: **29 passed, 0 failed**.
- Local `test_documents_postgresql`: **26 skipped** because this Windows environment has no disposable PostgreSQL service. The actual disposable PG evidence is Web #98.
- `py_compile` and `git diff --check` passed before documentation edits; the docs checkpoint must rerun the diff check.
- Server #112 / run `36688962707` at `dde82b0` failed in the generic HTTP regression step. Public annotations disclose no failing case and logs require sign-in; therefore it remains an unexplained CI failure, not a pass. Full local default discovery passed, and prior Server #111 passed. The next Server-triggering commit must rerun CI; diagnose any repeat using returned diagnostics before claiming green.

### NOT DONE

- A–D remain partially open, including owner override/settings UI, remaining alias and batch-economics functionality, further source-backed profitability/radar/productivity, trusted disabled-by-default timer implementation, and final integrated disposable PostgreSQL evidence at the eventual final SHA.
- Physical Android chooser/save/email check and production rollout are not verified here.
- Final all-workflow GitHub matrix and complete Part 12 regression are not yet done.

### EXTERNAL BLOCKER / MANUAL OWNER CHECK

- No current external blocker preventing software work. Do not run production release/cutover. Native device chooser check remains a manual owner check only; it is not a reason to stop the software work.

### EXACT NEXT

- Commit and push this evidence-only checkpoint after a fresh `git diff --check`; that will trigger a new Server run to replace unexplained Server #112. Then inspect `server/production_service.py`'s batch `economy()` plan/fact contract and continue the next source-backed B/C gap with targeted tests and a logical commit. Keep matrix counts **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌** until evidence justifies change. No autopilot completion/blocked flag; production cutover **NOT performed**.

## Latest automatic continuation checkpoint — 2026-09-30

Implementation is at `278fb2ed66fd41c6a5c6aadf08b79107962a0b15` on `codex-finalization-megapack-part12`; earlier sections below describe previous checkpoints, not the current HEAD. Roadmap counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**.

- Fixed the PostgreSQL reminder operator result contract at `06a7e93`: enabled runs now return their explicit enabled state for aggregation. Also corrected disposable test fixture cleanup and added a secret-safe exception-class diagnostic callback for explicit tests. The scheduler remains opt-in; no timer or external notification channel was enabled.
- Added Director approval/revocation and Packer denial UI evidence at `278fb2e`; the shared client UI sends no invitation list to the Packer role.
- Local evidence: Server discovery **265 run / 42 skipped / 0 failed**; reminder/operator **13/13**; infra readiness **8/8**; browser UI **31/31**; all Node/Android tests **52/52**; compileall, relevant JS syntax and diff checks passed. PostgreSQL integration tests are skipped locally because no disposable local PG is configured, not counted as passes.
- GitHub at `06a7e93`: Server #`36706201504` (Python 3.11/3.13) passed; Web #`36706201547` and its `documents-postgresql` job passed. At UI-only descendant `278fb2e`, Android UI #`36706427156` and APK #`36706426867` passed. The APK is staging `3.5-dev-staging`, versionCode 35, artifact/hash suffix `2e10ad7313b37f130eb493456cf51f453db2aa08b3c252c8d747422f2e60c481`. Server/Web source was unchanged after `06a7e93`.
- One failed Web PostgreSQL attempt at `2d319dd` is recorded transparently: CI pinpointed the missing `enabled` result field; the later named Web disposable-PG job passed after the fix. No production DB/service, DNS, release/cutover, secrets or phone was used.

**Not done:** Part 12 Definition of Done, remaining A–D acceptance, legacy identity and monetary REAL inventory/reconciliation, Windows installer, final VPS/owner visual gates and any production cutover. No complete/blocked flag is justified. Exact next: inspect Client 360 source-backed fields and write capabilities; add one missing block only if a canonical server source exists, with tenant/role/API/browser/disposable-PG coverage. If none is missing, inventory remaining `employee_id`/legacy `telegram_id` runtime boundaries without changing keys. See the latest progress section for the full next sequence.

## FOCUSED REPORT — canonical employee_id runtime — 2026-09-30

The canonical employee identity block has moved active user, manager-assignment, work and payroll request/response contracts to `employee_id`, with the retained legacy-table/history projection isolated in `server/employee_identity.py`. Excel import/template operations now call that adapter. No schema drop or historical payroll rewrite was made. A negative cross-company identity test was added to the disposable PostgreSQL/RLS suite.

### Final evidence for item 102

- At source `f7ccb72c0ae2556f9caa5765999ac7b4f43c1385`, the read-only scanner and its tests report **P0 external runtime 0, P0 direct runtime identity 0, P1 explicit bridges 50, P2 history/test references 129**. P1 bridges remain listed and covered; no destructive legacy-column removal was attempted.
- Web run `36714999102` passed both `web` and `documents-postgresql`. The disposable PostgreSQL job ran **30 tests, 2 skipped** and verified cleanup `db=0 roles=0 temp=0`. Its employee identity test checks canonical request/response identity and rejects a foreign employee ID where legacy IDs overlap across tenants.
- At this initial snapshot, Server run `36714999124` had Python 3.11 pass and Python 3.13 fail the unrelated invoice-XLSX idempotency assertion in `test_documents_api`. The later rerun at `05530ec` passed both versions; see “Latest follow-up — stable audit assertion and CI rerun” below.
- Roadmap/readiness item 102 is now ✅; total counts **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**.

### Current exact NEXT

Continue broader Part 12 work from the latest progress checkpoint: inspect remaining Client 360 source-backed editable/linked gaps, then legacy monetary REAL inventory/reconciliation, Windows thin client/installer, safe marketplace-news scheduler framework, and final release gates. The brittle audit substring test has been fixed, and Server Python 3.11/3.13 are green at `05530ec`; the earlier invoice idempotency failure did not reproduce. No Part 12 completion/blocked flag; no production cutover.

At the initial push, the refreshed read-only audit reported **0 P0 external runtime, 0 P0 direct runtime identity dependencies, 50 explicitly enumerated P1 bridges and 129 P2 historical/test references**. The disposable PostgreSQL case was then pending; its later green result and item-102 status are documented in “Final evidence for item 102” above.

Initial exact NEXT (superseded): push, check Web PostgreSQL and Server CI, and update item 102 from results. Continue remaining Part 12 work as set out in the current exact NEXT above; no production operation or autopilot flag was performed.

## Latest follow-up — stable audit assertion and CI rerun — 2026-09-30

- `05530ec85decac64675fe8593d3b2d7b6cf4531c` replaces a substring search for setting values in serialized audit events with exact allowlisted-key assertions; this avoids UUID/timestamp coincidence while still proving that no setting values are exposed. Its focused local audit test passed.
- At `05530ec`, Web run `36716682510` passed both `web` and disposable `documents-postgresql`. The PG job ran 30 tests (2 skipped), including the cross-tenant canonical employee-ID test, and verified cleanup `db=0 roles=0 temp=0`.
- Server run `36716682521` passed Python 3.11 and 3.13, each **268 tests, 42 skipped, 0 failed**. The earlier 3.13 XLSX idempotency assertion at `f7ccb72` did not reproduce; no product idempotency behavior was changed. The earlier failure remains recorded as transient.
- Latest readiness counts: **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. Item 102 is green; all P1 bridges remain explicit and retained.
- **Exact NEXT:** inspect Client 360 source-backed editable/linked gaps in `android_src/app/src/main/assets/production.js` versus `server/production_service.py`; then continue REAL-money inventory/reconciliation, Windows thin client/installer, safe marketplace-news scheduler, and final release gates. No completion/blocked flag; no production cutover.

## Focused revalidation — canonical employee_id runtime (2026-09-30)

The current branch revalidated the canonical identity boundary without changing runtime code. The assistant-branch map at `460e749` was read as historical evidence; its P0 count is superseded by the current scanner. `ops/employee_identity_migration_audit.py --fail-on-p0` reports P0 **0**, P1 **50** explicitly enumerated bridges, and P2 **129** history/fixture references. The P1 import/schema/history bridges remain retained. Migration-audit tests passed 8/8, canonical payroll adapter tests 2/2, full Server discovery 268 run / 43 skipped / 0 failed, infra readiness 8/8, and compileall passed on current documentation-only HEAD `70d9571`. Local disposable PostgreSQL was unavailable (30 tests skipped locally); the unchanged identity source already passed GitHub Web disposable PostgreSQL at `05530ec`, including the cross-tenant API contract and cleanup `db=0 roles=0 temp=0`. Item 102 remains ✅ and roadmap counts remain **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**.

**Exact NEXT:** inspect remaining Client 360 source-backed profile gaps, then inventory legacy money REAL fields and reconcile their active read/write paths against integer-minor-unit APIs. Preserve existing financial records; do not attempt destructive conversion. Continue Windows thin client/installer and remaining release software gates. No completion/blocked flag; no production cutover.
