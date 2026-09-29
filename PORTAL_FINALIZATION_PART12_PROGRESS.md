# PORTAL Part 12 progress checkpoint

## DONE

- Fetched `origin`; verified Part 11 base is `bc95a942021bb5c43d112f51d2c2e7881059b47a` and no newer remote Part 11 commit exists.
- Created isolated worktree `C:\Users\darta\Documents\PORTAL-Finalization-Part12` on `codex-finalization-megapack-part12`; source worktree was not changed.
- Cherry-picked `615495c3fef1f134ac651416f60b37809bda6380`; it contains exactly the three expected knowledge files.
- Read AGENTS, Knowledge Base, Constitution, roadmap, Parts 8–11 reports, and 3.4 candidate report.
- Confirmed payroll append-only settlement ledger and cent-based storage already exist with `server/test_payroll_settlement.py`; invitation UI, complete audit UI, multiple roadmap features and Windows installer are not yet proven complete.
- Selected 3.5 staging metadata because repository release metadata was still 3.4/34. Added Part 12 branch to Server/Web/Android build push triggers without changing security permissions or production release triggers.
- Extended the staging APK artifact contents with version metadata, changelog, checksum and a report generated only after workflow validations pass.
- APK SHA-256 is emitted in the GitHub Actions job summary and embedded in the public artifact name, alongside a `.sha256` file, so the exact staging artifact can be identified without API credentials.
- Added payroll XLSX «Выплаты» sheet from append-only settlement entries and integrated it through the active Documents generation route; item 52 moved to ✅ after unit and HTTP integration tests passed.
- Added a production cutover runbook, external blockers list, and this checkpoint. No production action was performed.

## NEXT

- Implement/test prioritized remaining feature gaps: reminder/job framework, accounts/invitations/audit UI and cross-client Documents.
- Build/test Windows thin client only after selecting an available supported toolchain; current local environment has no `dotnet` executable.
- Add provider-neutral off-server backup tooling and domain/reverse-proxy staging configuration; rehearse only with disposable resources.
- Update roadmap statuses from evidence, continue expanding release readiness matrix and report, run targeted/broad regression, compile/syntax/diff checks.
- Push follow-up commits, run/wait for GitHub CI, fix failures. Do not run production release workflow.

## TESTS

- `python -m unittest discover -s server -p 'test_*.py' -v`: 206 tests, 0 failures, 19 skipped (isolated PostgreSQL/VPS or ReportLab runtime gates unavailable locally).
- `python -m unittest test_report_xlsx -v`: 2/2 passed.
- `python -m unittest test_payroll_settlement.PayrollSettlementTest.test_payroll_xlsx_document_includes_settlement_sheet_and_payment_date -v`: 1/1 passed after wiring active Documents route.
- `python -m unittest test_payroll_settlement test_report_xlsx test_production -v`: 53 tests, 0 failures.
- `python -m compileall -q server android_src/tools`, JS syntax checks, and `git diff --check`: passed.
- `node android_src/tests/build-security.test.cjs`, employee-create-mode, native-shell, legacy-boundary, documents-chat checks: all passed.
- Full compile/syntax/diff checks are to be rerun after remaining implementation.
- Local shell lacks `dotnet`; no Windows installer build attempted.

## BLOCKERS

- External actions listed in `PORTAL_FINAL_EXTERNAL_BLOCKERS.md`.
- Production cutover is explicitly not performed.
- GitHub at `0cec960`: Android build #29, Server #39, and Web #11 succeeded; artifact `PORTAL_Android_3.5-dev_staging` was created (ZIP SHA-256 `9b9ad04e576985b7042ce76353e8e56f39d29e29d097e8bc4cc34885f276eba6`). Android UI #18 failed because its update-manifest fixture hard-coded the old 3.4 URL; the fixture now derives URL/version from release metadata and will be rerun.
- GitHub at `f963649`: Server #40 and Web #12 both succeeded.
- GitHub Android UI and APK build at `8408a33` succeeded. APK build #32 at `0eb573e` built the APK but artifact upload failed because hash-suffixed artifact name was incorrectly used as local file prefix. Fixed in `2b95dff`.
- Android build #33 at `2b95dff` succeeded. Artifact `PORTAL_Android_3.5-dev_staging_1804d3eaaeb95a87bd5424bf781f6cda767e1861bac004a43bba3126a884d054`; APK SHA-256 `1804d3eaaeb95a87bd5424bf781f6cda767e1861bac004a43bba3126a884d054`; ZIP SHA-256 `dd98bfb5532ceb3e80a70a63e866f7f904bdfe4a1cd151c4c17f3d9fa6473e01`.

## CONTINUATION №1 CHECKPOINT — 2026-09-30

### DONE NOW

- Continued in the existing Part 12 worktree/branch; starting checkpoint `42510ab` verified clean and current with origin. No other worktree was changed.
- Added `test_document_is_shared_between_independent_same_company_sessions` to `server/test_documents_postgresql.py`. It creates two independent auth sessions in company 1 and exercises create/list/metadata/download/archive/reflected archive over HTTP. This is an opt-in disposable PostgreSQL E2E and was **not executed locally**.
- Added shared Android/Web payroll settlement UI over the existing append-only `/api/v3/payroll-settlements` API: period totals, employee accrued/paid/balance, permission-gated payout, immutable history, and reversal event. No backend ledger/schema was replaced.
- Commits pushed to the Part 12 feature branch: `490be25` (Documents same-company cross-session E2E coverage), `0770275` (payroll settlement UI).

### PREVIOUSLY PROVEN

- Part 12 payroll settlement XLSX export and staging metadata/build 3.5/35 remain as documented above. Existing APK #33 evidence applies to `2b95dff`, not the new HEAD.
- Parts 1–11 evidence remains in its original reports; it is not recast as a new Part 12 run.

### TESTS RUN NOW

- `python -m unittest test_documents_api test_portal_documents test_postgresql_documents_schema -q` from `server/`: **21 passed, 0 failed**.
- `python -m unittest test_documents_postgresql -v` from `server/`: **7 skipped**, all require the opt-in isolated PostgreSQL runner; no PostgreSQL resource was created.
- `node --test android_src/tests/ui.test.cjs android_src/tests/documents-chat.test.cjs android_src/tests/documents-excel.test.cjs`: **17 passed, 1 skipped, 0 failed**; skip is local Playwright absence.
- `python -m unittest test_payroll_settlement test_report_xlsx -q` from `server/`: **27 passed, 0 failed**.
- `node --check android_src/app/src/main/assets/production.js`, `python -m compileall -q server`, and `git diff --check`: passed.
- One attempted Python invocation from repository root used server module names and failed to import; the same suites were rerun from `server/` and passed. No code/test failure resulted.

### GITHUB CI

- Push of `490be25` triggered Web checks #13 (run `36638474846`) and Server isolation #41 (run `36638474891`). At last observation, the public Actions listing showed server #41 in progress; final conclusions must wait for the runs after latest pushed SHA `0770275`.
- Push of `0770275` triggered asset-based UI/build workflows. CLI `gh` is absent; public Actions page is available but does not yet expose a final status for the latest SHA. Do not record CI as green until confirmed.

### NOT DONE / NEXT

- Block A: invitation/access-request lifecycle and UI, settings/active-seat management, company audit UI. Existing `employee_invites` is legacy Telegram-oriented and stores raw tokens; active app auth uses another model. Continue with an additive secure design, do not reuse legacy tokens.
- Block B: Client 360, effective-date tariff history UI/overlap tests, client/product rename history and catalog UI, batch economics and managed internal FBS/FBO/returns.
- Block C: receivables aging, canonical profitability, full dashboard/productivity, reminder scheduler. Settlement UI code is now present, but needs Web/Android role-flow tests and real PostgreSQL integration coverage.
- Block D: run the new same-company cross-session Documents E2E on a disposable PostgreSQL runner, expand UI folder/grouping/history/empty/error parity, finish Web Share path matrix, and recheck Android file contracts.
- Then run broad regression, verify all four latest-SHA CI gates including Android APK build, update evidence-based roadmap/matrix/report, and commit/push a clean checkpoint.

### EXTERNAL / ENVIRONMENT LIMIT

- Local machine has no installed WSL distribution or `psql`; the disposable PostgreSQL E2E could not run locally. No VPS runner/credentials are exposed via the available tools. This is an execution limitation, not evidence that the feature passes or a reason to stop software work.
- Production database/service/configuration, DNS, signing secrets and physical phone were untouched. Production cutover **NOT performed**.

Latest code checkpoint before Continuation №2: `8460c71` (branch pushed).

## CONTINUATION №2 — checkpoint `0006547` (2026-09-30)

### DONE NOW (not a claim that A or Part 12 is complete)

- Added additive Stage 10 `portal_access_invites` SQLite/PostgreSQL schemas. Invite token hash is stored; raw token is returned only once on initial create. Rows are tenant-scoped, PostgreSQL FORCE RLS protected, and terminal/history rows cannot be deleted or have identity fields rewritten.
- Added create/list/revoke/approve/reject and anonymous POST accept flow. Accept creates an inactive user; explicit approval activates through existing serialized active-seat enforcement. Tokens are company-prefixed, hashed at rest, expiry checked, replay-safe by request ID, and PIN is accepted only in POST body.
- Added shared Android/Web invite controls for create, existing/new employee binding, safe one-time copy/share, accept, pending list, approve, revoke and empty states. The raw token is held only in the one-time display sheet and is not persisted in app state.
- Added company access summary and existing-count display; enabled/suspended company check for authenticated mutations and invite acceptance. Existing owner company editor now exposes fee, demo dates, company/service state and seat limit; PORTAL limit remains unchangeable/unlimited. Server-side seat check and concurrency behavior remain in the existing save_user/save_company implementation.
- Added separate company and Platform Owner audit views with filters/pagination and safe summaries; lifecycle writes create audit entries without token/PIN data.
- Added Stage 10 to the disposable PostgreSQL Documents integration migration set and the isolated Stage 7 staging migration list. No PostgreSQL/VPS run occurred in this checkpoint.
- Committed and pushed `00065474fd5b0666810fd4defedfd9a17a374f8b` (`feat: add secure company invitations and audit views`); worktree was clean after commit.
- At that SHA, GitHub Server #42, Web #15, Android UI #21 and Android build #35 all completed successfully. Staging artifact: `PORTAL_Android_3.5-dev_staging_78a5df419939da5c41e208018f52a809b93bed1a9e29eba4db320317974111ca` (APK SHA-256 is the 64-hex suffix); artifact ZIP digest `35fa5c07b9acb6113254d8b705ed140159246b0db624adaeab82a6654607d8ab`.
- Added deterministic Web Share contract tests for cancellation (no forced download), unsupported-browser fallback, object URL revocation, and filename/MIME allowlist; included them in Web CI. This follow-up is local and pending its own commit/CI.
- No roadmap status was promoted. Items 10–12/15 remain 🟡 pending Web Playwright role flow, migration/PostgreSQL rehearsal, and remaining setting policy review.

### TESTS RUN NOW

- `python -m unittest test_production -q` from `server/`: **30 passed, 0 failed**.
- `python -m unittest test_portal_tenancy -q` from `server/`: **15 passed, 0 failed**, including limit, owner override, suspension and concurrent last-seat cases.
- `python -m unittest test_payroll_settlement test_report_xlsx -q`: **27 passed, 0 failed**; settlement role-matrix and payout XLSX tests rerun.
- Targeted invite lifecycle/role/scope/expiry/suspension tests are included above; hash-at-rest, no-token audit, consumed/revoked, owner explicit scope and login after approval passed.
- `node --test android_src/tests/ui.test.cjs android_src/tests/native-shell.test.cjs`: **9 passed, 1 skipped, 0 failed**; browser Playwright test skipped locally because Playwright is not installed.
- `node --test android_src/tests/web-adapter.test.cjs android_src/tests/web-share.test.cjs`: **6 passed, 0 failed**. A run including `web-smoke.playwright.cjs` could not load because local Playwright is absent; Web CI installs Playwright first.
- `node --check` for app/production/UI tests, `python -m compileall -q server`, and `git diff --check`: passed.
- PostgreSQL Stage 10 migration and actual web browser role flow remain pending. Android Gradle compile and the four GitHub workflows succeeded at `0006547`; later changes need separate verification.

### NEXT

- Commit/push the Web Share test follow-up and verify Web CI.
- Complete outstanding A parity/gates (company module-toggle policy if a supported model exists, owner/company audit browser checks, real Stage 10 PostgreSQL migration/invitation RLS rehearsal); update statuses only after evidence.
- Then continue B Client 360/tariff and product/production flows; C receivables/profitability/radar/reminders plus settlement role-flow; D Documents cross-client PostgreSQL run/UI/share/file contracts. Do not stop after CI.
- Before final completion, inspect/fetch and only then decide whether assistant infrastructure commit `1066c77` is safe to cherry-pick; do not duplicate its files.

### NOT DONE / EVIDENCE LIMITS

- A–D are not complete. No disposable PostgreSQL E2E, Web Playwright role flow, full regression, or VPS cleanup proof has run in this checkpoint.
- Local Playwright/psql/VPS execution remains unavailable; continue software work and use configured CI/test runners if provided.
- Production DB/service, DNS, signing secrets, and physical phone were untouched; production cutover **NOT performed**.

## NIGHT AUTOPILOT CONTINUATION №2 — checkpoint `b6b4092` (2026-09-30)

### DONE NOW

- Fixed the Playwright failure seen on `9bf3769`: the Client 360 Stage 3 fixture now grants the capabilities required to render the client card.
- Added company receivables aging API with integer-kopeck totals, partial payment handling, company-local due-date boundaries, aging buckets, client totals, client filter, and bounded pagination. Added shared-client aging view with client/bucket filters. Test covers boundaries, partial payments, cents reconciliation, pagination, and access denial.
- Added browser role-flow coverage for one-time invite token display, absence of PIN/token in request URL, and manager denial without `users.manage`.
- Commits pushed: `26e595d` receivables aging API/UI; `b6b4092` invite UI role-flow test; `a4b6052` docs checkpoint. Last tested code SHA: `b6b4092b0c867ecebbbc7b299be7e0fe8bb0cac6`; current clean branch SHA: `a4b6052` (docs-only after test run).

### TESTS AT THIS CHECKPOINT

- `python -m unittest discover -s server -p 'test_*.py' -q`: **212 passed, 20 skipped, 0 failures**. Skips include opt-in isolated PostgreSQL/VPS runs; no DB/role was created by this local run.
- Receivables boundary/partial-payment/cents/pagination unit test: **1 passed**.
- `node --test android_src/tests/ui.test.cjs`: **19 passed, 0 skipped, 0 failed** using local Playwright/Chromium.
- `node --test android_src/tests/web-share.test.cjs android_src/tests/ui.test.cjs`: **21 passed** at `26e595d`.
- JS syntax checks and `git diff --check`: passed.
- GitHub `26e595d`: Server #45, Web #19, Android UI #25, APK build #39 all success. GitHub `b6b4092`: Android UI #26 and APK build #40 success. Server source was unchanged by `b6b4092`; full server discovery passed locally at that SHA.
- No new disposable PostgreSQL E2E or cleanup rehearsal. Documents independent-session E2E and Stage 10 RLS tests remain unexecuted opt-in tests.

### ROADMAP / NEXT

- Numbered roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**; no items were promoted from code or mocked browser tests alone.
- A remains partial: full invite accept/approve/revoke role matrix, owner-audit coverage, settings/module policy review, and PostgreSQL RLS rehearsal.
- B remains partial: editable Client 360, tariff conflict/history proof, product CRUD, rename history, batches/plan-fact economics, and internal returns/FBS/FBO workflow.
- C remains partial: canonical profitability, director radar/productivity, reminders, and payroll settlement role/integration tests.
- D remains partial: Documents parity and actual disposable PostgreSQL two-session create/list/download/archive/cross-company denial E2E; Android contract and Excel regression need final-SHA rerun.
- Exact next: continue C source-backed metrics/reminder framework and D Documents parity/E2E setup, then B workflow/catalog, followed by A approval/settings/audit matrix. Run targeted and broad tests after each block, inspect migrations, push logical commits and verify CI.

**Not done:** A–D are not complete. PostgreSQL/VPS E2E and cleanup proof are missing. Production DB/service, domain/DNS, financial operations, signing secrets, physical device and production cutover remain untouched. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — checkpoint `aa94fa3` (2026-09-30)

### DONE NOW

- Added Documents virtual grouping in the shared UI by category, document type, month, and available client/employee identifiers; cards label current version versus archived record. No new filesystem behavior or tenant scope was added.
- Integrated assistant branch commit `1066c77` as `05ab65e`: provider-neutral pg_dump custom backup, pg_restore-list verification, SHA-256/manifest, optional age encryption, retention pruning, restore rehearsal restricted to `portal_test_restore_*`, nginx HTTPS reverse proxy template, hardened systemd backup timer and example environment file.
- Security follow-up `aa94fa3`: restore validation SQL output is no longer printed (it could contain returned business rows); backup prefix must be a simple filename prefix before retention deletion.
- D/UI and document contract tests passed; infrastructure helper tests passed. Branch is pushed; no conflict with existing ops/deploy files (none existed on prior HEAD).

### TESTS / CI EVIDENCE

- `node --test android_src/tests/ui.test.cjs`: **19 passed, 0 skipped, 0 failed** (includes Documents folders and revision/archive labels).
- `node --test android_src/tests/documents-excel.test.cjs android_src/tests/documents-chat.test.cjs android_src/tests/web-share.test.cjs`: **12 passed, 0 failed**.
- `python -m unittest ops.test_infra_readiness -v`: **7 passed, 0 failed**.
- `python -m compileall -q ops`, relevant JS `node --check`, `git diff --check`: passed.
- GitHub for tested UI SHA `e85078e`: Web #20, Android UI #27, APK #41 all success. No workflow ran for ops-only follow-up `aa94fa3`; server sources are unchanged since Server #45 success at `26e595d`. Full server discovery at `b6b4092`: **212 passed, 20 skipped, 0 failed**.
- No actual pg_dump/pg_restore or VPS rehearsal ran: no isolated PostgreSQL runner/credentials were available. No production backup target was configured or touched. The new helper unit tests use temporary files/mocked restore commands only.
- Roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No item was promoted from these tests.

### NEXT — continue without waiting

1. Block C: implement source-backed profitability/radar and company-scoped productivity tests; add the disabled-by-default reminder/job framework with idempotency, cadence, injected clock and retry state. Re-run payroll settlement role and XLSX tests.
2. Block D: run the existing real PostgreSQL two-session Documents E2E through an isolated runner when available; finish API metadata/history and UI pagination/filter/error cases, Web Share cancellation/fallback, Android FileProvider/save/share/email contract checks, and Excel regression.
3. Block B: complete product CRUD/archive/search, stable-ID rename/aliases, batch plan/fact and internal FBS/FBO/returns lifecycle. Block A: complete invite approve/revoke role matrix and audit/settings policy checks.
4. Then run new disposable PostgreSQL/RLS and backup-restore rehearsals only against `portal_test_*`; inventory legacy REAL money and employee_id/telegram_id boundaries; investigate thin Windows client and news operator scheduler; full final regression and CI.

**NOT DONE:** A–D remain incomplete; no Part 12 disposable PostgreSQL/VPS run or cleanup proof; no owner-visible artifact hash was fetched for latest APK. Tested code SHA: `aa94fa3`; current clean branch SHA: `c3b2588` (docs-only after tests). Production DB/service/DNS/financial operations/cutover remain untouched. No completion/blocked flag was created because software work remains.

## AUTOMATIC CONTINUATION — checkpoint `aa5cc64` (2026-09-30)

### DONE NOW

- `cec4536`: company audit filter UI now includes an entity ID and retains actor/action/entity/date selections when results reload.
- `320b6d9`: browser payroll settlement role-flow covers an authorized administrator adding a payment, refreshed paid/balance totals and retained prior payment history; a Manager with read capability but no payout capability sees no payment action and cannot post.
- `6137328`: Web Share tests cover successful file share with title/text, cancellation without forced download, unsupported/canShare-false safe download, object URL revocation, and filename/MIME rejection.
- `aa5cc64`: Playwright audit scenario submits actor, action, entity and date range filters and verifies every query parameter.
- No production data, service, secrets, signing material, domain or device was touched. No roadmap item status changed.

### TESTS / CI EVIDENCE

- `node --test android_src/tests/ui.test.cjs`: **20 passed, 0 skipped, 0 failed** at `aa5cc64`.
- `node --test android_src/tests/documents-excel.test.cjs`: **8 passed, 0 failed** at `320b6d9`.
- `node --test android_src/tests/web-share.test.cjs`: **5 passed, 0 failed** at `6137328`.
- `python -m unittest test_payroll_settlement -v` from `server/`: **25 passed, 0 failed**, including XLSX payment sheet, integer cents, snapshot immutability, idempotency, overpayment/concurrency and role/company isolation. An initial invocation from repository root failed module import because this suite expects `server/` as working directory; the corrected command passed.
- `node --check android_src/app/src/main/assets/production.js`, `node --check android_src/tests/ui.test.cjs`, and `git diff --check`: passed.
- GitHub API: commit `6137328` Web checks, Android UI, and APK build all succeeded. Commit `aa5cc64` Android UI and APK build both succeeded; its Web workflow was not triggered by the UI-test-only path change. Earlier commit `cec4536` had Web, Android UI and APK green. Latest Server workflow remains #45 at `26e595d`; server source was unchanged in these commits.
- Disposable Documents PostgreSQL test was **not run**. This checkout had no `psql`, no configured test database DSN, and no opt-in PostgreSQL E2E environment flag; no DB/role/temp resource was created. No available isolated VPS runner was found in the repository workflow configuration. Production DB/service remained untouched.

### NOT DONE / EXACT NEXT

- D: execute `server/test_documents_postgresql.py` through an isolated disposable PostgreSQL runner for same-company two-session create/list/download/archive and cross-company denial; finish any parity gaps and capture DB/role/temp cleanup proof. This is still a test execution gate, not a reason to stop other code work.
- C: implement the disabled-by-default company-scoped reminder/job framework (cadence, idempotency, injected clock, retry/run metadata) and add reconciliation/time/duplicate tests. Profitability/radar/productivity require further source-backed review; do not invent missing allocations or values.
- B: product CRUD/archive/search, canonical rename/alias history, batch plan/fact and generic FBS/FBO/return lifecycle remain incomplete. A: invitation approval/revocation/settings/owner-audit role matrix and PostgreSQL RLS proof remain incomplete.
- Then inspect legacy REAL-money fields and employee_id/telegram_id runtime boundary, run backup restore only on disposable resources, and complete final regression/CI/roadmap evidence.
- Roadmap remains **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**; this checkpoint promotes nothing.
- Branch `codex-finalization-megapack-part12` code SHA `aa5cc64` has green Android UI and APK build checks and is pushed. This docs update is uncommitted and must be committed/pushed before ending the turn. No completion/blocked flag is appropriate.

Production cutover **NOT performed**.
