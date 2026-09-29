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

## Continuation №2 delta — SHA `b6b4092`

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
