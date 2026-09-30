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
- Branch `codex-finalization-megapack-part12` tested code SHA `aa5cc64` has green Android UI and APK build checks and is pushed; this checkpoint records its regression/audit evidence without changing source. No completion/blocked flag is appropriate.

Production cutover **NOT performed**.

### Regression / identity-money audit update — source SHA `aa5cc64`

- Full server discovery from `server/`: `python -m unittest discover -s . -p "test*.py"` — **212 passed, 20 skipped, 0 failed**. Skips include the opt-in disposable PostgreSQL/VPS integrations. This source tree is unchanged at docs checkpoint `8f0d56e`.
- Full Node test files `*.test.cjs`: **41 passed, 0 failed, 0 skipped**. Web workflow-equivalent adapter/share/smoke set: **9 passed**. `python -m compileall -q server ops`, all **5** workflow YAML parses, JS syntax and `git diff --check` passed.
- Read-only runtime audit found `telegram_id` remains used by legacy endpoints in `server/portal_app_server.py` for employee linkage, assignments, work, payroll and summaries. Stage 3 code prefers `employee_id`, but compatibility fallback and historical `telegram_id` storage are still live; item 102 cannot be closed.
- New finance paths use integer minor units for payroll settlements/receivables, but legacy routes still call `float(...)` for work economics, cost/stock consumption and payroll summaries. No full deployed SQLite `REAL` inventory was run, and no cents migration was attempted. Item 105 remains 🟡.
- **Exact NEXT:** implement and test the disabled-by-default internal reminder runner, then continue B stable-ID product/rename/batch workflow gaps and A approval/settings/owner-audit coverage. Keep the real Documents PostgreSQL cross-session test and cleanup proof as an isolated execution gate; continue software work while that runner is unavailable. Finish with legacy money/identity remediation design only after all use sites and historical data are inventoried.
- Roadmap counts unchanged: **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No completion/blocked flag created. Production cutover **NOT performed**.

## Block A targeted addition — code/test SHA `2ca0ad0`

- Added backend API integration coverage for company audit entity/date filters, actor/action match, pagination with descending chronology, redacted summaries, and forbidden packer/forged-company access.
- `python -m unittest test_production -v` from `server/`: **32 passed, 0 failed** (includes the new audit test). Full server discovery immediately before this test-only addition was **212 passed, 20 skipped, 0 failed**.
- GitHub server isolation and Web workflows for `2ca0ad0` were in progress at the last poll; Android source did not change. Do not claim those workflows green until checked.
- Exact NEXT stays: disabled-by-default reminder runner and B product/name/batch workflow gaps; then complete A settings/owner-audit coverage and D disposable PostgreSQL cross-session proof. No test status or roadmap count was promoted by the mocked/test-fixture browser work.

## AUTOMATIC CONTINUATION — verified checkpoint `c09e44a` (2026-09-30)

### DONE NOW

- `a8bfcdc` and `c09e44a`: shared Web UI coverage verifies director/admin invite controls can approve a pending access request and revoke an unused invite; test waits for server-state rerender before asserting action controls disappear.
- `2ca0ad0`: server test covers company audit filters, safe summary, chronological pagination and company/role denial. `b9e8aca` fixed a nondeterministic security test that searched PIN digits as a substring across UUID/JSON; it now checks exact values and sensitive key names.
- Payroll UI role-flow, audit UI filters, Web Share behavior, Documents/Excel and Android native source contracts remain covered. No production data/configuration/secrets were touched.

### TESTS / CI

- Full Node `*.test.cjs` suite at `c09e44a`: **42 passed, 0 failed, 0 skipped**. Browser `ui.test.cjs`: **21 passed**.
- Web adapter/share/smoke set: **9 passed**. Payroll settlement server tests: **25 passed**; production API suite with new audit test: **32 passed**; activity suite: **4 passed**.
- GitHub Server workflow run `36648295612` at `b9e8aca`: Python 3.11 **213 passed, 19 skipped**; Python 3.13 **213 passed, 19 skipped**. Both matrix jobs green. GitHub Web checks at `b9e8aca` green.
- GitHub Android UI and staging APK build at `c09e44a` both green. APK versionName `3.5-dev-staging`, versionCode `35`, buildNumber `3.5`.
- Staging artifact `PORTAL_Android_3.5-dev_staging_73596aedbcf1cec9145df112478acced79f48a07150142eae1bdbe042d7cae35`; APK SHA-256 `73596aedbcf1cec9145df112478acced79f48a07150142eae1bdbe042d7cae35`; GitHub artifact archive digest `sha256:37bdd26c826a39104f1d0752f0c71d260b8f36b3fa541a41fbbbd566cf7c1794`. Artifact run: https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36648676231
- The earlier server failure at `2ca0ad0` was a flaky substring assertion against `1234` in a session UUID; fixed and both CI matrix jobs pass at `b9e8aca`. The earlier Android UI failure at `a8bfcdc` was a rerender race in the new invite test; fixed and UI/APK pass at `c09e44a`.
- Real disposable PostgreSQL Documents E2E, backup/restore VPS rehearsal, database cleanup proof: **not run**. This environment has no `psql`, test DSN or opt-in runner. No disposable DB/roles/temp fixture were created. Production DB/service remain untouched.

### NOT DONE / EXACT NEXT

- C: build the disabled-by-default company-scoped reminder runner with cadence, idempotency, injectable time, retry/run metadata; extend source-backed productivity/radar only where source facts support it.
- D: execute the existing independent-session Documents E2E against a disposable PostgreSQL runner; capture list/download/archive consistency, other-company denial and cleanup proof; complete any remaining revision/history parity.
- B: product CRUD, canonical rename/alias history, batch plan/fact and generic FBS/FBO/return lifecycle remain incomplete. A: company settings/limit owner/director UI matrix and owner-audit policy remain incomplete.
- Legacy identity/money audit found active legacy `telegram_id` and float calculations; preserve columns/history and design an additive strategy only after full deployed schema/source reconciliation.
- Roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No completion/blocked flag is appropriate. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — checkpoint `af29605` (2026-09-30)

### DONE NOW

- Added `server/reminder_jobs.py`, an opt-in scheduler primitive: disabled by default, explicit company scope, daily/weekly cadence with configured UTC offset, stable per-company reminder keys, duplicate suppression through caller-provided tenant storage, and retry after failed delivery. Exception text and reminder payload are not logged by this module. It does not start a timer, query business records or enable production delivery.
- Added 5 deterministic tests for disabled mode, scope validation, local-date cadence, idempotency, duplicate suppression and failed-delivery retry.
- Committed/pushed as `af296054d61f8a08fa4f109bc050a8693a8c417b` (`feat: add opt-in reminder scheduling primitives`). No migrations were added.

### TESTS / CI

- `python -m unittest test_reminder_jobs -v` from `server/`: **5 passed, 0 failed**.
- Full `python -m unittest discover -s . -p "test*.py" -q` from `server/`: **218 passed, 20 skipped, 0 failed** (177.014 seconds). Skips include opt-in PostgreSQL/VPS gates; this run created no database or role.
- `python -m compileall -q reminder_jobs.py test_reminder_jobs.py` and `git diff --check`: passed.
- GitHub Server Isolation run **#49 / 36649752281** at `5df9dc0` passed on Python 3.11 and 3.13; each job ran **218 tests, 19 skipped, 0 failed**. GitHub Web run **#26 / 36649752347** at the same SHA passed. Android source did not change; prior Android UI/APK green at `c09e44a` remains the last Android evidence.
- Staging build remains `3.5-dev-staging` / versionCode 35 with previously reported APK hash `73596aedbcf1cec9145df112478acced79f48a07150142eae1bdbe042d7cae35`; no new APK was built for this backend-only change.

### NOT DONE / EXACT NEXT

- Reminder item 47 remains ⏳: add source-backed overdue-invoice/unbilled-work selectors, tenant-persistent run/attention records and operator timer wiring; then test the real persistence/retry path. The new framework is a tested primitive, not an enabled scheduler.
- D: find/enable an isolated disposable PostgreSQL runner for the existing two-session Documents create/list/metadata/download/archive and cross-company denial test; prove DB/role/temp cleanup. No `psql`, DSN or VPS runner is available in this execution environment, and none was created.
- Continue B product CRUD/aliases/batch plan-fact/returns and A owner/director settings plus owner-audit role coverage. Then complete C profitability/productivity/radar, real settlement PostgreSQL coverage, Android/Web final contracts, and broad CI/regression.
- Roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No status promotion and no autopilot flag. Production cutover **NOT performed**.

### Follow-up fix — code SHA `5df9dc0`

- Tightened the reminder callback contract after review: duplicate check and notification persistence must now occur atomically inside a tenant-scoped `dispatch_once(company_id, reminder, key)` callback. This avoids a check-then-send race between concurrent runners; failed callback attempts remain retryable. The runner does not claim to supply this database transaction itself.
- `python -m unittest test_reminder_jobs -v`: **5 passed, 0 failed**; compile and `git diff --check` passed. Follow-up committed/pushed as `5df9dc0ec52abc6245bf642b7ddad7c607094849` (`fix: make reminder dispatch contract atomic`).
- Full Node regression at `5df9dc0`: `node --test` over all `*.test.cjs` — **42 passed, 0 failed, 0 skipped** (includes Playwright Chromium UI role, payroll, invite, Documents/Excel, and Web Share scenarios).
- Full local server discovery result above belongs to `af29605` before this callback-contract-only follow-up. Latest-SHA GitHub server isolation suite now passed as listed above. Latest SHA Android source is unchanged.

### A audit UI follow-up — SHA `1f3adc5`

- Added Playwright coverage for the separate Platform Owner audit surface: it is entered from the owner companies view, shows owner-only safe-summary wording, and sends company/actor/event/date filters to `/api/platform/audit`.
- `node --test android_src/tests/ui.test.cjs`: **22 passed, 0 failed, 0 skipped**.
- Pushed commit `1f3adc5edbf19f37204fcc056bc467ea970ae62e` (`test: cover platform owner audit UI`). Android UI workflow **#34 / 36650177640** and staging APK workflow **#48 / 36650177613** both passed.
- Latest artifact: `PORTAL_Android_3.5-dev_staging_a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; APK SHA-256 `a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; artifact ZIP digest `sha256:cdae0e6c93bbe0d714c73a4f41e2fd910c7819bb9a75906073a367e00d0b38c8`. Version `3.5-dev-staging`, versionCode 35, build 3.5.
- Server #49 and Web #26 are green at parent `5df9dc0`; commit `1f3adc5` changes only browser tests. No production target changed.
- Exact NEXT: continue actual A settings/owner policy enforcement and B catalog/batch/return workflows; finish C reminder persistence/candidates, profitability/productivity; run D independent-session Documents PostgreSQL E2E on a safe disposable runner and prove cleanup. Do not treat mocked browser or prior Parts 8–11 E2E as new Part 12 PostgreSQL evidence.

### Automatic continuation — secure invitation PostgreSQL coverage — 2026-09-30

#### DONE NOW

- Confirmed starting branch was clean at `2c1aad2` and synchronized with origin. Continued in the existing Part 12 worktree.
- `854520f` adds a real disposable PostgreSQL + HTTP API lifecycle test for Stage 10 invitations: one-time token hash at rest, idempotent create retry without re-displaying the token, company-scoped list, forged company header denial, cross-company accept denial, accept/approval/login, consumed-token denial, and audit redaction.
- `da28db0` adds an independently authenticated company packer session and verifies that a user without `users.manage` cannot create an invitation.
- Both commits are pushed. No migration or production resource was changed.

#### TESTS / CI

- Local targeted lifecycle/authorization/expiry suite: `python -m unittest test_production.ProductionTest.test_secure_invite_lifecycle_hashes_token_is_idempotent_and_scoped test_production.ProductionTest.test_invite_revoke_and_role_capability_denials test_production.ProductionTest.test_invitation_expiry_and_suspended_company_fail_closed -v` — **3 passed, 0 failed**.
- Full `python -m unittest test_production -v` — **32 passed, 0 failed**.
- Local `python -m unittest test_documents_postgresql -v` — **8 skipped** because this workstation has no `psql`, disposable PostgreSQL admin DSN, or enabled integration gate. No local database or role was created.
- GitHub Web checks **#33 / 36651996603** at `da28db0`: Web and `documents-postgresql` jobs **success**. The PostgreSQL job ran `test_documents_postgresql` with the ephemeral PostgreSQL 16 service. Its eight tests include six passing API/database tests and two expected gates skipped (real PDF and browser-in-fixture).
- The preceding PostgreSQL run **#32 / 36651817020** at `854520f` also completed successfully. Fixture cleanup verifies disposable database=0, roles=0 and temp files=0 after each successful run.
- GitHub Server isolation **#55 / 36651996627** at `da28db0`: Python 3.11 and 3.13 jobs **success**. Web check #33 also validates current SHA. No Android sources changed; staging remains 3.5-dev-staging / versionCode 35 and was not rebuilt for this server-test-only change.
- `python -m compileall -q server` and `git diff --check` passed. Worktree was clean after the code commits.

#### NOT DONE / EXACT NEXT

- A remains partial: implement/verify allowed company settings and owner module/fee/demo/state/limit policy, owner audit PostgreSQL authorization, and full new/existing employee plus director/owner invitation role matrix. Do not promote roadmap 10–12 or 15 from this one integration test.
- B remains software work: product catalog lifecycle, stable-ID rename/alias history, batch plan/fact completeness and generic FBS/FBO/returns.
- C remains software work: persistent reminder candidates/dispatch, source-backed profitability/productivity/radar and payroll settlement PostgreSQL role-flow coverage.
- D: same-company Documents cross-session create/list/metadata/download/archive and cross-company denial now passed in the disposable PostgreSQL job; remaining Web Share/Android file contract and full shared Documents UI parity stay open.
- Continue with A settings/owner audit policy and targeted tests, then B/C gaps. Reconcile roadmap only after the larger affected workflows are proven. Current roadmap counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No autopilot flag. Production cutover **NOT performed**.

### Automatic continuation №2 — A settings/owner audit PostgreSQL proof — 2026-09-30

#### DONE NOW

- Continued from clean, pushed `c12a4f1`; no other worktree was changed.
- `d31d760` fixes PostgreSQL test helper invocation: `make_conninfo` is called through `type(self)` so Python does not bind the fixture instance as a positional argument.
- `d853677` adds standard company limit=15 to the synthetic external tenant, verifies over-limit user creation is rejected through HTTP `/api/users`, active count remains unchanged, and forged company scope is denied. It also keeps a PostgreSQL Platform Owner audit test proving owner login event filtering and denial for company admin/packer.
- GitHub Web #39 validates both added A tests against the isolated PostgreSQL service. No application migration was added and no production resource was used.

#### TESTS / CI

- Local A service/tenancy regression: **4 passed** (`company-access`, 15-seat/override, concurrency last seat, owner audit authorization).
- Local `python -m unittest test_documents_postgresql -v`: **10 skipped** without local PostgreSQL opt-in; no local database/role was created.
- GitHub Web **#39 / 36653710143** at code SHA `d853677`: Web and `documents-postgresql` jobs **success**. PostgreSQL fixture: **10 tests, 8 passed, 2 skipped** (real PDF and in-fixture browser gates); cleanup verified **db=0 roles=0 temp=0**.
- GitHub Server **#61 / 36653710121** at `d853677`: Python 3.11 and 3.13 both **221 tests, 22 skipped, 0 failed**.
- The earlier Web failures #34–#37 were isolated to the new test code calling the stored `make_conninfo` function through an instance. `d31d760` corrected the binding; Web #38 proved the owner-audit scenario and Web #39 proved both A PostgreSQL scenarios. They did not require application/security changes.
- `python -m unittest test_production.ProductionTest.test_company_access_summary_is_capability_and_owner_scope_checked test_portal_tenancy.CompanyIsolationTest.test_company_limits_activation_and_individual_override test_portal_tenancy.CompanyIsolationTest.test_concurrent_last_seat_cannot_exceed_company_limit test_portal_tenancy.CompanyIsolationTest.test_owner_explicit_technical_access_is_audited_without_secrets -v`: **4 passed**.
- `python -m compileall -q .` from `server/` and `git diff --check`: passed. No Android/Node files changed; no APK rebuild.

#### NOT DONE / EXACT NEXT

- A: the existing model has no company module-toggle field/policy, and director company settings UI is not complete. Implement a defined, additive module settings model with server enforcement and role/audit tests; then expand invite coverage for Platform Owner explicit-company and existing-employee paths.
- B: Client 360 edit/detail completeness, tariff overlap/historical snapshot checks, product lifecycle/aliases, batch economics and generic FBS/FBO/returns remain software work.
- C: payroll settlement role/E2E, persistent reminder candidates/dispatch, canonical profitability/productivity/radar remain software work.
- D: real same-company Documents sync passed earlier; complete remaining shared UI revision/filter parity and Web Share/Android contracts.
- Roadmap remains **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**. No status promotion, no completion/blocked flag. Production cutover **NOT performed**.

#### Owner explicit-scope follow-up — `ea531c5`

- Added Platform Owner invitation API checks in PostgreSQL: create without explicit company selection returns 403; selecting company 2 allows only that scoped create and returns a company-prefixed one-time token. Existing company admin/packer denial and owner-audit filter checks remain in the same disposable fixture.
- Targeted local invitation role tests: **2 passed**. The PostgreSQL fixture test is locally skipped (no local PostgreSQL); `python -m compileall -q .` and `git diff --check` passed.
- GitHub Web **#40 / 36654066963** at `ea531c5`: Web and disposable PostgreSQL jobs success; fixture **10 tests, 8 passed, 2 skipped**, cleanup DB=0/roles=0/temp=0. Server **#62 / 36654067004**: Python 3.11/3.13 both **221 tests, 22 skipped, 0 failed**.
- Exact next: complete remaining existing-employee invitation matrix and determine/implement company module-toggle model + director settings UI, then continue B and C software work. No roadmap status promotion or autopilot flag; production cutover **NOT performed**.

## Automatic continuation — payroll PostgreSQL role coverage — 2026-09-30

### DONE NOW

- Starting state was clean and synchronized at `a3e380b`; continued on the existing Part 12 branch/worktree. No production resource was touched.
- `f2b39cc` makes the invoice XLSX retry test reuse one request ID so it verifies an identical HTTP retry, not a new request with a randomly generated key. This fixes the single Server #64 failure without changing product code or security checks.
- `d64f965` adds a real HTTP/PostgreSQL payroll settlement role-flow test: administrator payout on a closed period, packer write/read denial, foreign-company denial, same-request idempotency, exact accrued/paid/balance values, and closed-snapshot immutability.
- `042a6fb` uses PostgreSQL `pg_typeof()` for the minor-unit storage assertion. The first run caught a test portability error (`typeof()` is SQLite-only); after correction, disposable PostgreSQL passed.
- Updated roadmap wording for item 11 to record the existing-employee link proof without claiming the full invitation role matrix complete. Counts remain **72 ✅ / 34 🟡 / 8 ⏳ / 12 🔌**.

### TESTS / CI

- At `f2b39cc`, Server #66 / `36655075254`: Python 3.11 **222 tests, 23 skipped, 0 failed**; Python 3.13 **222 tests, 23 skipped, 0 failed**.
- At `f2b39cc`, Web #43 / `36655075340`: Web and disposable PostgreSQL jobs succeeded; PostgreSQL fixture **11 tests, 2 skipped**, cleanup **DB=0 roles=0 temp=0**.
- At `042a6fb`, Web #45 / `36655538735`: Web and disposable PostgreSQL jobs succeeded; PostgreSQL fixture **12 tests, 2 skipped**, cleanup **DB=0 roles=0 temp=0**. The two skips are the existing real-PDF and browser-in-fixture opt-in gates.
- Targeted local Documents/schema tests: `python -m unittest test_documents_api test_portal_documents test_postgresql_documents_schema -q` — **21 passed, 0 failed**.
- Local invocation of the new PG test is expected to skip without `PORTAL_DOCUMENTS_PG_INTEGRATION=1` and an isolated PostgreSQL DSN; it created no DB/role. `python -m compileall -q server` and `git diff --check` passed before pushes.
- Server #67 / `36655538742` at `042a6fb`: Python 3.11 and 3.13 each **223 tests, 24 skipped, 0 failed**.
- The `d64f965` Web #44 PostgreSQL job had one test-only failure because `typeof()` does not exist in PostgreSQL; fixture cleanup still confirmed **DB=0 roles=0 temp=0**. Corrected in `042a6fb` and verified by Web #45.

### NOT DONE / EXACT NEXT

- First confirm Server #67 / `36655538742` outcome and record both Python test counts. If it fails, diagnose/fix and rerun.
- Commit/push this evidence-only documentation update after CI is settled; verify clean worktree and synchronized origin.
- Continue software tasks: A module-toggle/server policy and director settings UI plus remaining invitation/audit role matrix; B product CRUD, aliases/rename, batch economics and managed internal returns/FBS/FBO; C persistent source-backed reminder candidates, profitability/radar/productivity; D remaining Documents revision/filter parity and Android/Web file/share contracts.
- Existing same-company Documents cross-session E2E and invitations/seat-limit PostgreSQL proofs are already in prior Web jobs; do not describe them as newly unrun. Backup restore/VPS rehearsal and final Android build remain separate gates.
- No roadmap status was promoted. No completion/blocked flag created. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — product catalog and honest batch plan — 2026-09-30

### DONE NOW

- Started from pushed clean `e6c80e3`; fetched `origin` and confirmed it was current. Added client-scoped product catalog with stable IDs, create/rename/archive/search, capability enforcement, duplicate-active-name guard, product selection for new batches, and immutable product-name snapshots on existing batches.
- Added additive PostgreSQL Stage 12 to permit only product catalog metadata edits in the shared production ledger immutability trigger. The staging migration list and disposable PostgreSQL fixture include Stage 12; no legacy or production data was backfilled or rewritten.
- Corrected batch economics: when no plan rows exist, plan and variance are null and the shared UI labels them “Недоступно”; actual values remain source-backed. Per-unit amounts use integer kopecks with deterministic half-up rounding.
- Commits pushed: `c5e75ec` (`feat: add stable client product catalog`), `4e38943` (`fix: show missing batch plan as unavailable`). Roadmap item 35 moved to ✅ only after service, browser, and disposable PostgreSQL verification; counts are now **73 ✅ / 33 🟡 / 8 ⏳ / 12 🔌**.

### TESTS / CI AT `4e38943cb8e9262e95701081f6ffc3f6ca5a7f5c`

- `python -m unittest discover -s server -p 'test_*.py' -q`: **228 passed, 27 skipped, 0 failed**; opt-in PostgreSQL/PDF gates account for skips.
- `node --test`: **46 passed, 0 skipped, 0 failed**, including full Playwright UI/browser scenarios, Web Share contracts, Android native file-source contracts, and shared role flows. Focused UI separately passed **25/25**.
- `python -m unittest ops.test_infra_readiness -v`: **7 passed, 0 failed**.
- Targeted product catalog and batch economics tests passed; Stage 12 PostgreSQL product test is in the successful Web disposable PostgreSQL job.
- `python -m compileall -q server ops android_src/tools`, relevant `node --check`, all workflow YAML parsing, and `git diff --check`: passed.
- GitHub Server `36658950142`, Web `36658950177` (Web and `documents-postgresql`), Android UI `36658950145`, and APK build `36658950150`: all success. Staging remains `3.5-dev-staging`, versionCode 35. Artifact `PORTAL_Android_3.5-dev_staging_7d0a6bf83b17054b9f53697c1fb69e77de90ebefa55c1ca2988a001548efed65`; APK SHA-256 `7d0a6bf83b17054b9f53697c1fb69e77de90ebefa55c1ca2988a001548efed65`; ZIP SHA-256 `f9a644f2b3fccafc88fd4fdf4ee000240390e3894dfd52e215222fe31dea8c67`.
- No local PostgreSQL server/disposable DSN was available; local opt-in PG fixtures were skipped without creating resources. The remote Stage 12 fixture ran against the workflow disposable PostgreSQL service. No production DB/service, DNS, secrets, or physical device was touched.

### NOT DONE / EXACT NEXT

- A remains partial: complete director settings policy and remaining invitation/access/audit role paths, including fresh PostgreSQL tests where needed.
- B remains partial: tariff effective-date/conflict/history coverage, stable client rename/alias history, complete batch economics inputs, and generic internal FBS/FBO/returns workflow.
- C remains partial: source-backed profitability/productivity/radar completeness and reminder candidate persistence/dispatch. The runner primitive is not an enabled production scheduler.
- D: preserve prior same-company cross-session Documents PostgreSQL success; complete remaining revision/filter UI parity and any Android/Web file/share contract gaps not covered by the new `node --test` pass.
- Next implementation: build tenant-scoped, source-backed reminder candidate selection and persistence/idempotency integration from overdue invoices and unbilled completed work; add isolated PostgreSQL tests, then continue B and remaining A/D gaps. Do not create autopilot completion/blocked flags. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — reminder source/sink — 2026-09-30

### DONE NOW

- Added reminder candidates from tenant-visible overdue invoices (remaining balance after payments, including partial payments) and completed-but-unbilled work. Company-local date handling includes timezone-offset due timestamps.
- Added an atomic `Repository.insert_once` path and append-only `notifications` records keyed by reminder/cadence. Duplicate retries return `false`; manager finance/invoice roles see persisted reminders in `PORTAL Сегодня`, workers without those capabilities do not.
- Commits pushed: `cd22c20` candidate collection and tenant insert-once; `2db871e` authorized dashboard visibility; `e08e0d8` simplified the PostgreSQL test to focus on persistence/idempotency/isolation.
- No timer, operator scheduler, last-run record, or production enablement was added. Item 47 remains ⏳; no roadmap counts changed.

### TESTS / CI

- `python -m unittest test_reminder_jobs -v`: **7 passed, 0 failed**.
- Combined reminder and dashboard visibility tests: **8 passed, 0 failed**.
- `python -m unittest test_documents_postgresql -q` locally: **15 skipped**, because no local disposable PostgreSQL is configured; no local DB/role was created.
- Full local server discovery at `e08e0d8`: **232 passed, 28 skipped, 0 failed**.
- GitHub Web `36660208411` passed both Web and `documents-postgresql`; PostgreSQL fixture verifies cleanup DB=0, roles=0, temp=0. GitHub Server `36660208403` passed Python 3.11 and 3.13. No Android source changed after its 3.5/35 success at `4e38943`.
- Two earlier Web PG runs (`36659765933`, `36659903107`) failed while testing the new scenario. Public summaries exposed only exit code 1, so the initial fixture failure's precise cause is unknown. The final scenario isolates atomic ledger insertion and cross-company visibility and passes; no authorization or CI gate was weakened.
- `python -m compileall -q server ops android_src/tools` and `git diff --check`: passed.

### EXACT NEXT

- Add safe operator-run cadence/last-run/retry records and a deterministic scheduled entry point that stays disabled by default. Prove failure/retry and concurrent duplicate suppression on disposable PostgreSQL.
- Then continue B tariff conflict/history, canonical client rename/aliases, batch FBS/FBO/returns; A director settings and remaining role matrix; C unified profitability/productivity/radar; and D remaining document parity.
- Roadmap remains **73 ✅ / 33 🟡 / 8 ⏳ / 12 🔌**. No completion/blocked flag. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — director metrics and tariff proofs — 2026-09-30

### DONE NOW

- Continued from the clean pushed checkpoint `9c41aa8`; current code checkpoint is `7917dacffaf1e0241595ccd63ab0336dbf43568a` on the existing Part 12 branch/worktree.
- `b307c32`: expanded PORTAL Сегодня with company-local today/month volume, revenue/payroll, open/overdue invoice totals, closed-period payout balance and honest unavailable-plan profit. Added aware-date handling in dashboard/receivables and tests.
- `da4b493`: added disposable PostgreSQL HTTP coverage for dashboard facts and company isolation.
- `635e692`: verified tariff effective boundary, duplicate effective timestamp denial and preservation of prior work snapshots; added the same scenario to the disposable PostgreSQL fixture.
- `2548d97`: surfaced team units/hour only from work rows with recorded durations; UI explicitly displays “Нет данных времени” if duration data is missing.
- `7917dac`: financial monthly trend buckets use the company's configured UTC offset; a month-boundary regression proves a UTC September work row can correctly belong to local October.
- GitHub disposable Web/PostgreSQL, Server, Android UI and staging APK all passed at `2548d97`. Artifact: `PORTAL_Android_3.5-dev_staging_481dc11b4d9fcb1bd6cbef87a29605feab42ac6fb72fbe1a8886f71f57502f74`; APK SHA-256 is the artifact's 64-hex suffix. Server #83, Web #61, Android UI #41, APK #55.
- At `7917dac`, Server #84 and Web #62 passed. The Android assets were unchanged after the successful `2548d97` UI/APK run; only server date aggregation changed afterward.
- Roadmap evidence text for 19 and 44–47 was refreshed. Item 47 moved from ⏳ to 🟡 because the tested disabled-by-default runner, persisted cadence/run/retry records and tenant idempotency now exist; the trusted system timer and persistent company cadence configuration remain incomplete. Numbered checklist is now **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**.

### TESTS AT CURRENT CODE

- `python -m unittest discover -s server -p 'test_*.py' -q`: **244 passed, 31 skipped, 0 failures** at `7917dac`.
- `node --test android_src/tests/*.test.cjs`: **47 passed, 0 skipped, 0 failed** at `2548d97` (no Node code/test changed in `7917dac`). Focused browser UI: **26 passed**.
- `python -m unittest ops.test_infra_readiness -q`: **7 passed**.
- New focused tariff effective-date and local-month tests passed. `python -m compileall -q server ops android_src/tools`, Node syntax checks, YAML parsing, and `git diff --check` passed.
- Local `test_documents_postgresql` remains opt-in and skipped because this workstation has no isolated PostgreSQL DSN; it created no DB/role. GitHub Web jobs execute the fixture with `portal_test_web_*`, restricted NOSUPERUSER/NOBYPASSRLS roles, and teardown assertions for DB=0/roles=0/temp=0. Web #61 passed the dashboard/tariff cases.
- No production DB/service, DNS, financial transaction, credential, signing key, or physical phone was touched.

### NEXT (SOFTWARE WORK REMAINS)

- A: finish invitation/settings/audit full capability matrix and remaining company-owned settings policy review.
- B: complete Client 360 editable/linked blocks, aliases/search normalization, remaining batch plan/fact source coverage and managed FBS/FBO workflow details.
- C: finish profitability aggregation/reconciliation and period comparisons; reminder runner is still operator-invoked and has no active timer. Do not enable it in production.
- D: finish Documents history/filter parity; same-company cross-session PostgreSQL E2E was proven in earlier Web CI and must not be misreported as a new run in this checkpoint.
- Continue then through legacy employee_id/telegram_id and REAL-money inventory/reconciliation, marketplace-news disabled operator framework, backup restore rehearsal and final docs/release gates. Windows installer and production cutover remain open.
- Next exact action: inspect and close an additional B/C gap with targeted tests; then commit/push and poll workflows. After that, refresh final readiness reports with exact tests/CI, leaving a clean checkpoint. No completion/blocked flag; no production cutover.

## AUTOMATIC CONTINUATION — director settings access and save flow — 2026-09-30

### DONE NOW

- Starting HEAD `d8e2cbd` was clean and synced with origin. Added a shared Settings entry to the existing company control screen, shown only when the authenticated capability list includes `company.settings`; the existing server remains the tenant authority and receives no client-forged company ID.
- Browser flow now proves a Director with `company.settings` can open the screen, read the existing schedule values, save a changed value, and submits without a `company_id`; a Manager without the capability does not see the entry.
- Server role/scope test proves Director GET/POST succeeds, Manager GET/POST is denied, and forged `X-Portal-Company` is denied.
- Commits pushed: `ae9f83f` capability-gated company settings entry; `50a9e3e` browser save-flow coverage; `2a0ab8f` server role/scope coverage. Worktree clean and branch synced at `2a0ab8f570de3a79ce6513df334ed284c1384b42`.
- Roadmap item 12 remains 🟡: only existing schedule/presence settings were surfaced; this does not complete every company setting or its production rollout. Overall counts remain **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**.

### TESTS / CI

- `node --test android_src/tests/ui.test.cjs`: **27 passed, 0 skipped, 0 failed** after the settings save-flow assertion.
- `node --test android_src/tests/*.test.cjs`: **48 passed, 0 skipped, 0 failed** at the settings UI code checkpoint.
- `python -m unittest test_production.ProductionTest.test_control_schedule_and_uninvoiced_separate_from_debt -v`: **1 passed**; `python -m compileall -q .` from `server/`: passed.
- Full `python -m unittest discover -s server -p 'test_*.py' -q` on current server code: **246 passed, 33 skipped, 0 failed**. Skips are opt-in external/PDF gates; local run created no PostgreSQL DB/role.
- `python -m unittest ops.test_infra_readiness -q`: **7 passed**; `python -m compileall -q server ops android_src/tools`, relevant `node --check`, and `git diff --check`: passed.
- GitHub Server run `36667262958` and Web run `36667263031` at `2a0ab8f`: success. Android UI run `36667166698` and APK build run `36667166789` at `50a9e3e`: success. APK artifact: `PORTAL_Android_3.5-dev_staging_d34c2d8fd3714ffa6deae9ae6cec26e46879937d6d5b09bfe7e30d330301fdd4`; APK SHA-256 is the suffix `d34c2d8fd3714ffa6deae9ae6cec26e46879937d6d5b09bfe7e30d330301fdd4`; build remains 3.5-dev-staging/versionCode 35.
- Disposable PostgreSQL feature evidence remains the successful `4f62ba7` Web run `36666482298` for source-backed profitability reconciliation, and earlier named Stage 10/12/Document runs in the matrix. No new PostgreSQL resources were created locally in this continuation; production DB/service and DNS untouched.

### NOT DONE / EXACT NEXT

- A remains partial: complete remaining invitation/audit role policy matrix and broader director settings; Platform Owner module toggles stay owner-only.
- B remains partial: Client 360 editable blocks, client normalization/alias coverage, full batch economics inputs and generic FBS/FBO workflow completion.
- C remains partial: full unified client/batch/company profitability UI, period comparisons and trusted timer/company cadence enablement for reminders; keep production scheduler disabled.
- D remains partial: existing same-company independent-session PostgreSQL success stands; continue Documents history/filter parity and final Android/Web file contracts.
- After software gaps, finish employee_id/telegram_id runtime-boundary audit, legacy money-field cents inventory/reconciliation, marketplace news operator framework, backup restore rehearsal, Windows installer, and final release evidence. No autopilot flag: software work remains. Production cutover **NOT performed**.
