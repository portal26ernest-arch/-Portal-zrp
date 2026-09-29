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
