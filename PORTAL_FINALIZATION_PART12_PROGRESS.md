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

## AUTOMATIC CONTINUATION — Documents client/employee filters — 2026-09-30

### DONE NOW

- Added virtual Documents filters for client ID and stable employee ID. Client filtering appears only with `clients.read`/`clients.manage`; employee filtering appears only with `users.manage`/`payroll.all`. Submitted values use the existing tenant-scoped server query; no company selector/header was added.
- Playwright proves both filters are sent together for an authorized admin and both are absent for a user with only `documents.read`. Added server regression for canonical employee ID filter and foreign-company query denial.
- Commits: `3223ad0` UI + browser role assertions; `ba9035a` employee filter server regression; `c732067` fixes the payroll XLSX idempotency test to reuse its request ID. Branch clean/pushed at `c7320674f4cd033f4e60ad16a7286cae7a69596a`.
- No roadmap promotion; counts remain **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**.

### TESTS / CI

- `node --test android_src/tests/ui.test.cjs`: **27 passed, 0 skipped, 0 failed**.
- `node --test android_src/tests/*.test.cjs`: **48 passed, 0 skipped, 0 failed**.
- `python -m unittest test_documents_api test_portal_documents test_postgresql_documents_schema -q`: **22 passed, 0 failed** on successful repeat; `python -m compileall -q .` from `server/` and `git diff --check`: passed.
- One preceding Documents-suite attempt had **21 passed/1 failed** because the payroll slip XLSX retry supplied a new request ID; fixed in `c732067`, then the 22-test suite passed. The first Server CI at `ba9035a` caught the same test-only issue; fixed and rerun green.
- GitHub Web `36668181017` at `ba9035a`: Web and disposable PostgreSQL jobs passed. PostgreSQL fixture ran **20 tests, 18 passed, 2 skipped** (real PDF and in-fixture Chromium gates), and confirmed cleanup `db=0 roles=0 temp=0`. It included independent same-company session Documents create/list/metadata/download/archive and cross-company denial.
- GitHub Server `36668180785` at `c732067`: Python 3.11 and 3.13 both **247 tests, 32 skipped, 0 failed**. Android UI `36667824748` and APK `36667824984` at `3223ad0` passed; APK artifact `PORTAL_Android_3.5-dev_staging_d9a8def27b9365eda12d419aefcd95f40831d31715e56626577e6391116f57a5`, SHA suffix `d9a8def27b9365eda12d419aefcd95f40831d31715e56626577e6391116f57a5`, version 3.5-dev-staging/versionCode 35.
- Local Documents PG opt-in tests created no resources. Real PostgreSQL execution used GitHub's disposable test fixture; cleanup assertions passed. No VPS/production DB or service was used.

### NOT DONE / EXACT NEXT

- A: complete remaining invite/audit role policy matrix and broader director settings; current director UI only exposes existing schedule/presence settings.
- B: finish Client 360 editable blocks, normalization/alias history completeness, full batch economics and managed FBS/FBO lifecycle.
- C: finish unified source-backed profitability UI and productivity period comparison; persistent reminder cadence/system timer remains absent/disabled.
- D: document revision/history parity beyond current revision labels, then retain existing cross-session PG E2E and file/share contracts in final regression.
- Continue employee_id/telegram_id runtime-boundary and legacy monetary REAL inventory/reconciliation, news operator framework, backup restore rehearsal and Windows installer. No autopilot flag; software work remains. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — client aliases and shipment lifecycle — 2026-09-30

### DONE NOW

- Starting HEAD was `056e1e88598bb740302c490fe263afac9e321ebe`, synced except prepared roadmap/matrix alias evidence. CI at `056e1e8`: Web #75 plus disposable PostgreSQL, Android UI #48, and staging APK #62 passed. APK artifact `PORTAL_Android_3.5-dev_staging_d5c65948ad3a2909eb394c1330fab23d66efa48cbe51236ad3715cbcd7ad7e2d`; APK SHA-256 is the 64-hex suffix; version remains 3.5-dev-staging/versionCode 35.
- `056e1e8` adds Knowledge Base client spelling aliases to search without changing canonical client rows or persisting guessed aliases. Item 33 remains 🟡.
- `e85928e` adds service and disposable PostgreSQL HTTP coverage for FBS/FBO shipment completion: stable idempotency retry, conflicting request reuse rejection, tenant/role denial, single shipment row and audit record. Playwright confirms the shared UI submits the selected shipment direction with a request ID.
- Local tests: shipment service **1 passed**; UI Playwright **28 passed**; full Node suite **49 passed**; Server discovery **249 passed, 34 skipped, 0 failed**; ops infra readiness **7 passed**. PostgreSQL shipment fixture was skipped locally because no disposable local PostgreSQL is configured. Compileall, relevant Node syntax check and `git diff --check` passed.
- At `e85928e`, GitHub Web #76 (including disposable PostgreSQL), Android UI #49, APK build #63, and Server #93 (Python 3.11 and 3.13) passed. APK artifact `PORTAL_Android_3.5-dev_staging_daf9604d76bdf2f4bea40b065302ae6020371da6f49e8a74676b575b7aee7839`; APK SHA-256 is the 64-hex suffix. The isolated PostgreSQL fixture asserts DB=0, roles=0, temp=0 at teardown. No local database/role was created.

### EXACT NEXT

- Item 32 is ✅ after the verified assignment → work → FBS/FBO shipment → return lifecycle, HTTP/service/browser coverage, audit, tenant/role denial and idempotency. Counts are **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**.
- Continue A invitation/audit capability coverage and director-owned settings; B editable Client 360 blocks and broader alias/history coverage; C source-backed profitability/productivity comparisons and persistent reminder cadence/timer; D document revision/history UI parity.
- Then complete employee_id/telegram_id runtime audit, legacy REAL money inventory/reconciliation, marketplace news operator framework, backup restore rehearsal, Windows thin installer and final integrated checks.
- Production resources remain untouched; no complete/blocked flag is justified while software work remains. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — Client 360 requisites and productivity period comparison — 2026-09-30

### DONE NOW

- Starting branch HEAD was `a4dd960` after fetch; worktree changes were the already-started Client 360 requisites implementation. No new worktree was created.
- `819dbfb` adds the `client-requisites` read/write API over the existing company-scoped `portal_client_requisites` table; it does not introduce a duplicate table/model. Writes require `clients.manage`, reads require `clients.read`, target only the authenticated company/client, preserve partial updates, use command request-ID idempotency, and reject unknown/nontext fields. Audit records only `client.requisites.updated` plus the client ID; field values, bank account and tax identifiers are not included.
- Shared Client 360 UI reads and edits requisites under the existing capability, provides empty/current form values, and refreshes from server after save. Browser role test verifies `clients.read` alone does not show edit; POST body has stable client ID and no forged company selector.
- Added the live disposable PostgreSQL session/RLS test to the existing isolated Web fixture; it checks two same-company sessions, company B returning no company A values, forged company header denial, idempotent retry, and audit redaction. It skipped locally because there is no local disposable PostgreSQL service/DSN.
- `f5475ae` adds optional analytics date-range comparison against the immediately preceding equal-length window. Dates are interpreted with the company UTC offset. Work units use source rows; units/hour uses only rows with valid positive duration, and comparative pace remains unavailable if either window lacks timing. Shared UI exposes date filters and explicit period labels.
- Roadmap counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; neither item 17 nor 46 was promoted. There is no complete/blocked flag; A–D and other software work remain.
- Commits pushed in order: `819dbfb` (`feat: edit tenant-scoped client requisites`), `f5475ae` (`feat: compare productivity across company periods`).

### TESTS / CI

- Client API target: **1 passed**; Client requisites Playwright included in UI suite.
- At `819dbfb`, server full discovery: **253 passed, 36 skipped, 0 failures**; browser UI **28 passed**; full Node suite was run before the follow-up C increment and passed **49/49**. Ops infra tests **7/7**; compileall and diff-check passed.
- GitHub at `819dbfb`: Server `36677295945`, Web `36677295988`, Android UI `36677295987`, Android APK `36677295995` all succeeded.
- Analytics API target: **1 passed**; browser comparison test passed. After both blocks, full server discovery: **254 passed, 36 skipped, 0 failures**; focused browser UI **29/29**; full Node suite **50/50**; infra readiness **7/7**; compileall, relevant node checks and `git diff --check` passed.
- GitHub Web `36678086685` and its `documents-postgresql` job completed successfully at `f5475ae8d95f5f6e29e21acecc55d1bac3422c61`; that disposable PostgreSQL job ran `test_documents_postgresql` and passed. Web teardown uses fixture assertions for database/role/temp cleanup. Android UI `36678086723` and APK build `36678086692` also passed. The staging artifact is `PORTAL_Android_3.5-dev_staging_67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`, with APK SHA-256 equal to the suffix `67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`. Server run `36678086835` remains in progress. Version remains 3.5-dev-staging/versionCode 35.

### NOT DONE / EXACT NEXT

- A remains partial: complete remaining invitation/access role matrix, settings policy, and owner/company audit flows.
- B remains partial: finish Client 360 source-linked sections/edit controls and broader client/employee normalization; retain item 17 🟡.
- C: after the period comparison, implement/verify additional profitability/reconciliation and disabled-by-default reminder cadence/retry/operator execution; do not enable a production timer.
- D remains partial: wait for Web disposable PostgreSQL to execute the new Client requisites RLS/audit test, then complete revision/history/filter parity and final Android/Web file contracts.
- Exact next software step: poll the four workflows on `f5475ae`; diagnose any failure, then continue C reminder cadence/source-backed profit or A authorization coverage. After CI is green, refresh these checkpoints with run IDs, then commit/push the docs checkpoint.
- Broader remaining work: employee ID/legacy telegram ID runtime audit, REAL money inventory and additive cents reconciliation strategy, disabled news operator framework, disposable backup restore rehearsal, Windows thin client/installer, and final full regression. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — Client 360 Documents drilldown — 2026-09-30

### DONE NOW

- `b588462` adds a Client 360 action to open the shared Documents screen filtered to that stable client ID. The documents list uses the existing server `client_id` query filter; it does not add a second client/document store or use Android-only APIs. The action requires document access and client read/manage capability; the documents screen continues enforcing document capabilities.
- Browser regression exercises the authorized Client 360 flow and asserts the resulting canonical `/api/v3/documents?...client_id=1` request and selected client filter. UI suite: **29 passed, 0 failed**. Full Android/Node suite: **50 passed, 0 failed**. `node --check` passed for both changed JS files; `git diff --check` passed.
- `f5475ae` Server `36678086835`, Web `36678086685`, Android UI `36678086723`, and Android APK `36678086692` all completed successfully. Web's disposable PostgreSQL job passed. Staging APK artifact is `PORTAL_Android_3.5-dev_staging_67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc` (SHA-256 `67015a4feea9246b8d0ee04d0e964f8071a2a77bbdedaa6339b3d98dd59572dc`); version remains 3.5-dev-staging/versionCode 35.
- Roadmap count remains **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Item 17 remains 🟡 because broader Client 360 acceptance is open. No production systems or disposable production resources were used.

### PREVIOUSLY PROVEN

- `819dbfb` tenant-scoped Client 360 requisites API/UI and PostgreSQL fixture coverage; `f5475ae` productivity period comparison; evidence and test totals remain recorded in the preceding progress entry.
- Existing Documents cross-session PostgreSQL test ran in Web CI at `f5475ae`; do not count that old result as a run for `b588462`.

### NOT DONE / EXACT NEXT

- A invitation/access/settings/audit policy matrix remains partial.
- B Client 360 still needs remaining source-backed linked/editable sections and normalization/history coverage; item 17 stays 🟡.
- C needs additional profitability/reconciliation and reminder cadence/operator execution; production timer stays disabled.
- D needs revision/history UI parity and final share/file contracts; cross-session PG test must run on the eventual final source SHA.
- Exact next: poll Server/Web/Android UI/Android APK workflows for `b588462`; fix any software failure. Then continue invitation/settings role-coverage or reminder cadence, followed by targeted tests and commit. No completion or blocked flag is warranted while software work remains. Production cutover **NOT performed**.

### Integration regression follow-up

- Full server discovery at code SHA `967e947` (identical server files to `f5475ae`): **254 tests, 36 skipped, 0 failures**. One earlier run concurrent with `ops.test_infra_readiness` showed a single non-reproducible document idempotency assertion; the exact test passed alone and the complete suite passed when rerun without the concurrent operation. No API limit or assertion was weakened.
- `ops.test_infra_readiness`: **7/7 passed**; `python -m compileall -q server android_src tools ops` passed.
- CI at the code ancestor `b588462`: Web #`36678773323`, Android UI #`36678773573`, APK #`36678773473` all succeeded. The Server workflow is path-triggered and was green at `f5475ae` (#`36678086835`), where the server code used by `b588462` was unchanged. The Web workflow includes and passed the disposable PostgreSQL documents job at `f5475ae` (#`36678086685`). Docs checkpoint SHA `967e947` changes no source files.

## AUTOMATIC CONTINUATION — Client 360 receivables drilldown — 2026-09-30

### DONE NOW

- `64dc650` adds a Client 360 action to open existing receivables aging for that client. It requires `invoices.read`, resets pagination and bucket filters, closes the profile sheet, and requests the canonical server endpoint with `client_id`; no invoice math or source facts are synthesized.
- The browser role flow validates the filtered API request and selected client, then calls the action under a `clients.read`-only role and asserts denial. Browser UI suite **29/29 passed**. Full Android/Node suite **50/50 passed**; relevant `node --check` and `git diff --check` passed.
- Prior current source SHA `b588462` has Web #`36678773323`, Android UI #`36678773573`, APK #`36678773473` green. New SHA `64dc650` workflows at check time: Web #`36680058456`, Android UI #`36680058499`, Android APK #`36680058649` running. Server files are unchanged since successful Server #`36678086835` at `f5475ae`. Staging version remains 3.5-dev-staging/versionCode 35.
- Roadmap counts stay **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; items 17 and 42 remain 🟡. No release flag; production remains untouched.

### EXACT NEXT

- Poll all three `64dc650` workflows and Web disposable PostgreSQL job. Fix software failures rather than reporting them as gates.
- A still needs complete role/settings/audit policy coverage; B still needs other source-backed Client 360 fields and normalization; C still needs broader profitability/reconciliation and persistent disabled-by-default cadence/operator scheduling; D still needs final documents revision/history/filter role coverage and a disposable PG run at final code SHA.
- After the new CI result, continue one of those blocks with targeted tests, commit and push; keep the roadmap counts unchanged until additional acceptance evidence supports a status change. No complete/blocked flag while these software tasks remain.

### GitHub CI finalization for this checkpoint

- At code SHA `64dc650f5818d891d27e95e99c1d471f6e50923e`, Web #`36680058456` (including `documents-postgresql`), Android UI #`36680058499`, and Android APK #`36680058649` all completed successfully.
- The Server workflow did not trigger because this commit changed only Android/Web JS and browser tests. Server files are unchanged from `f5475ae`, where Server #`36678086835` passed; local full Server suite at current source: **254 passed, 36 skipped**.
- Web GitHub job logs were unavailable via anonymous API (403); report only the green named PG job. Prior source fixture cleanup assertions at earlier Web PG runs remain prior evidence, not new cleanup-count output for this run.
- `64dc650` APK remains staging 3.5-dev-staging/versionCode 35. Artifact/hash already recorded above from successful b588462 APK; no distributable changed in this source-only UI commit.

## AUTOMATIC CONTINUATION — invitation decision role matrix — 2026-09-30

### DONE NOW

- Starting HEAD was `bd8222b`, clean and synced. Confirmed the preceding settings/capability audit changes and PostgreSQL fixture restoration passed Web #`36681705904` (including `documents-postgresql`) and Server #`36681705913`.
- `510becd` adds safe company audit events for settings and permission changes; summaries contain only changed field names, never setting or capability values. `bd8222b` restores the mutable settings/capability fixture after the new PostgreSQL test.
- Added an invitation decision role matrix in `6c6c4ee`: a Director can approve an accepted request in the same company; a packer cannot list, approve, or revoke; company B cannot decide a company A invite by known ID; a forged company header is rejected; repeated approval does not duplicate the audit event. The SQLite regression also proves a Manager cannot revoke, a Director can revoke idempotently, and a revoked token cannot be accepted.
- Roadmap counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. No item was promoted from this role-coverage increment.

### TESTS / CI

- Targeted `test_production.ProductionTest.test_invite_revoke_and_role_capability_denials`: **1 passed**. The first local attempt exposed a duplicate test-token setup; removed the redundant setup and reran successfully.
- Full Server unittest discovery at `6c6c4ee`: **258 tests, 39 skipped, 0 failed** (208.224 seconds). New opt-in PostgreSQL cases skip locally because no disposable local PostgreSQL service/DSN is configured.
- `python -m unittest test_documents_postgresql -q`: **26 skipped locally**, all gated on disposable PostgreSQL configuration; it does not constitute local live-PG evidence.
- `python -m unittest ops.test_infra_readiness -q`: **7 passed**. `python -m compileall -q server android_src tools ops` and `git diff --check`: passed.
- Web #`36682830228` passed both `documents-postgresql` and `web`; Server #`36682830272` passed Python 3.11 and 3.13. Web #`229650a` was an earlier failed test attempt: the test expected the decision response under `data.invite`; API returns the invite directly in `data`. Corrected in `6c6c4ee` and rerun green.
- `bd8222b` Web #`36681705904` and Server #`36681705913` passed before the role matrix. Staging version remains 3.5-dev-staging/versionCode 35; no APK rebuild was triggered by server-only test changes.

### PREVIOUSLY PROVEN

- Existing same-company independent-session Documents PostgreSQL E2E and teardown evidence remains attributed to the earlier Web job listed in the readiness matrix; it was not rerun as a final Part 12 gate in this checkpoint.
- Assistant infra helper `1066c77` is already integrated; infra readiness was rerun above. No production DB/service/DNS/signing material or phone was used.

### NOT DONE / EXACT NEXT

- A: complete the remaining Platform Owner and Director settings/audit role matrix; production rollout is not claimed.
- B: complete remaining source-backed Client 360 sections, durable normalization/alias history, and missing batch plan/fact economics evidence.
- C: finish unified profitability/source coverage and reminder cadence configuration/operator execution; production reminder timer remains disabled.
- D: complete document revision/history UI parity and run the cross-session PostgreSQL E2E on the eventual final tested source SHA.
- Exact next implementation: inspect the shared Documents revision/history screen and add browser assertions for revision ordering, current/archived labels, and denied history access; run targeted UI/server tests, then commit and push. Continue A–D after this test block; do not stop at this checkpoint. No completion/blocked flag. Production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — settings/owner audit PostgreSQL evidence — 2026-09-30

### DONE NOW

- Starting HEAD was `ad487710768b577d1f711e81e72730eedc7d8c75`, clean and synced with origin. The new settings role checks initially posted without the API's standard `request_id`; commit `166fa35` now uses the shared helper and explicit ids for denied POSTs.
- `dde82b0` expands Platform Owner audit PostgreSQL coverage: same-day company/actor/event filters, one-row pagination across two pages, distinct rows, and existing role denial/secret exclusion.
- Current Documents implementation already had the previously requested history UI coverage: browser checks verify revision order, archived/current labels, read-only history visibility, and denial before an unauthorized history API call. The real PostgreSQL class also exercises cross-session revision/archive behavior.
- Readiness counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. No status was promoted by test-only evidence.

### TESTS / CI

- `166fa35`: full `test_production` **45 passed**; `test_documents_postgresql` **26 skipped locally** because no disposable PG is installed; `py_compile` and diff check passed. Web #`36688493231` (run 97) passed `web` and `documents-postgresql`; Server #`36688493277` (run 111) passed Python 3.11 and 3.13.
- `dde82b0`: `test_portal_tenancy` **16 passed**; `test_documents_postgresql` **26 skipped locally**; compile and diff check passed; browser UI **29/29 passed**. Web #`36688962524` (run 98), including disposable PostgreSQL, passed.
- Server #`36688962707` (run 112) failed at the generic HTTP regression step; anonymous job logs expose only exit code 1. The same complete local discovery on the source passed **259 tests, 39 skipped, 0 failed**. Prior Server #111 at `166fa35` passed. Do not describe #112 as green; the next pushed Server-triggering checkpoint must re-run it and inspect any available detail.
- No production DB/service, secrets, signing material, or phone was used.

### PREVIOUSLY PROVEN

- Reminder cadence is tenant-persisted and disabled by default from `fcbc3ba`; the runner consumes the configured setting and does not start a production timer or external messaging.
- Documents same-company two-session create/list/metadata/download/archive and company-B denial remain proven only at the earlier named Web PostgreSQL run in the readiness matrix; the Web run at #98 newly covers settings/audit and history fixtures, not a claim of exact disposable-resource counters.

### NOT DONE / EXACT NEXT

- A: remaining owner/subscription and user-limit override controls, plus full UI role checks for invites/settings/audit.
- B: complete Client 360 facts, canonical alias-history matching, and planned-versus-actual economics role/UI coverage.
- C: remaining source-backed dashboard/profitability/productivity coverage and a trusted system timer that remains disabled for production by default.
- D: Android native save/share/email visual check is manual; run final disposable PostgreSQL suite on final source SHA and retain cleanup evidence.
- Exact next: update readiness/progress/report evidence for `166fa35`/`dde82b0`, run `git diff --check`, commit/push the docs checkpoint (triggering a fresh Server CI after #112), then continue B/C source inspection. Never infer the #112 failure cause from incomplete logs. No completion or blocked flag; production cutover **NOT performed**.

## AUTOMATIC CONTINUATION — reminder PostgreSQL operator and invitation UI role proof — 2026-09-30

### DONE NOW

- Starting HEAD was `2d319ddf27f9ae698a97069339b2b5c5b9f060b9`, clean and synced after fetch. Confirmed assistant infrastructure commit `1066c77` is already integrated; did not repeat it.
- `5c2b711` fixed the disposable PostgreSQL reminder test's settings cleanup and added a test-only diagnostic hook that emits only company ID and exception class, never exception text or tenant data. Web disposable PostgreSQL exposed the application contract bug: enabled-run results lacked `enabled`, which the operator aggregator reads. `06a7e93` adds that explicit boolean and unit assertions; saved reminder settings remain disabled by default and no timer/external sender was enabled.
- `278fb2e` extends the invitation browser role flow: Director approves/revokes an accepted/pending invitation; Packer receives no invitation list and cannot decide one. This complements existing server/PostgreSQL tenant, role, idempotency, and audit checks.
- Readiness counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. No roadmap status was promoted from this incremental operator/UI coverage.

### TESTS / CI

- Reminder/operator tests: **13 passed**; full Server unittest discovery at `06a7e93`: **265 run, 42 skipped, 0 failed**; `ops.test_infra_readiness`: **8/8 passed**; `python -m compileall -q server android_src/tools ops` passed.
- Browser UI suite after `278fb2e`: **31 passed**; full Node/Android suite: **52 passed, 0 failed, 0 skipped**; `node --check android_src/tests/ui.test.cjs` and `git diff --check` passed.
- GitHub Web #`36706201547` passed `web` and `documents-postgresql`; disposable PG Server/Web source is `06a7e93`. GitHub Server #`36706201504` passed Python 3.11 and 3.13. At UI-only descendant `278fb2e`, Android UI #`36706427156` and staging APK #`36706426867` succeeded. No Server/Web source changed after `06a7e93`.
- Staging artifact: `PORTAL_Android_3.5-dev_staging_2e10ad7313b37f130eb493456cf51f453db2aa08b3c252c8d747422f2e60c481` (SHA-256 suffix `2e10ad7313b37f130eb493456cf51f453db2aa08b3c252c8d747422f2e60c481`), version 3.5-dev-staging/versionCode 35. No production DB/service, cutover, DNS, secrets or phone test runner was used.
- Local `test_documents_postgresql` remains **29 skipped** because no local disposable PostgreSQL is configured; the named GitHub disposable PostgreSQL job is the live evidence above. The first Web gate at `2d319dd` failed; `5c2b711` made it diagnosable and `06a7e93` fixed it, after which the named job passed.

### PREVIOUSLY PROVEN

- Batch plan/fact API in integer minor units, tenant/role denial and missing-plan behavior were already implemented. Web PostgreSQL #`36706201547` passed `test_batch_economy_reconciles_integer_plan_fact_and_tenant_scope`; browser coverage at `278fb2e` retains unavailable-vs-zero behavior and margin/per-unit rendering. Item 28 remains 🟡 because plan-input/source completeness has not been fully accepted.
- Client 360 requisites, task/document/receivables drilldowns; Documents revision/history UI and PostgreSQL cross-session tests; reminder disabled-by-default cadence/systemd examples; assistant infra work remain as recorded in earlier entries.

### NOT DONE / EXACT NEXT

- A: remaining owner/Director settings and invitation/audit policy matrix and rollout checks.
- B: item 17 Client 360 still has source-backed editable/linked blocks to finish; item 33 canonical client/employee normalization and alias migration remain partial; item 28 plan-entry/source completeness remains open.
- C: source-backed company/warehouse profitability, productivity quality/radar comparisons and deployment-owned timer/activation remain open; reminder systemd files are examples only and production dispatch remains disabled.
- D: complete Android native chooser/save/email visual check remains an owner visual check; run the full disposable PostgreSQL gate again on the eventual final code SHA.
- Broader remaining work: employee_id/telegram_id runtime-boundary audit, legacy monetary REAL inventory/reconciliation, Windows thin-client/installer, final VPS/release gates. Counts stay **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; no completion/blocked flag. Production cutover **NOT performed**.
- **Exact NEXT:** inspect remaining Client 360 fields and write capabilities in `android_src/app/src/main/assets/production.js` against `server/production_service.py`; select one missing block only if its values already have a server source, then add scoped API/UI/browser and disposable PostgreSQL coverage. If inspection finds no such source-backed gap, produce a read-only `employee_id`/legacy `telegram_id` runtime-boundary inventory before changing identifiers. Run targeted and full relevant tests, commit and push each logical block.

## FOCUSED BLOCK CHECKPOINT — canonical employee_id runtime — 2026-09-30

- Current source: `f7ccb72c0ae2556f9caa5765999ac7b4f43c1385`; clean, fetched branch matches origin.
- Closed roadmap item 102: audit remains P0 external runtime **0**, P0 direct identity **0**, P1 **50** explicitly enumerated and retained behind the adapter/import/schema/history boundaries, P2 **129**. The scanner audit test suite passes **8/8** and `--fail-on-p0` passes.
- GitHub Web run `36714999102` at `f7ccb72`: Web and `documents-postgresql` succeeded; disposable PostgreSQL ran **30 tests, 2 skipped**, including `test_employee_identity_api_contract_is_canonical_and_company_scoped`; cleanup verified `db=0 roles=0 temp=0`. The Server Python 3.11 job at run `36714999124` passed. Its Python 3.13 job failed one unrelated XLSX invoice idempotency assertion (`request_id уже использован для другого документа`); do not report the overall Server matrix as green.
- Local regression attempt from the correct `server/` directory ran 110 tests and exposed a separate brittle audit test (`test_company_settings_and_capability_changes_are_audited_without_values`) that checks secret-value substrings against UUIDs. The identity tests/scanner pass; this settings-test failure and the CI XLSX issue remain independent follow-ups. Local PostgreSQL is not installed; disposable PG evidence is the named CI run above.
- Readiness counts now **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. Production data, schema drops, DNS, cutover, and secrets were not touched.
- **Exact NEXT at this snapshot:** continue Part 12 at the existing broader NEXT: inspect Client 360 remaining source-backed editable/linked blocks; if none, proceed to money `REAL` inventory/reconciliation, Windows thin client/installer, safe marketplace-news scheduler, and release gates. Separately fix the settings audit test's substring false positive and diagnose/retest invoice XLSX idempotency before asserting Server matrix green. The audit test fix and green rerun are now recorded in the latest checkpoint below. No Part 12 completion/blocked flag; production cutover **NOT performed**.

## FOCUSED CONTINUATION — canonical employee_id runtime — 2026-09-30

### DONE IN THIS BLOCK

- Starting repository state was HEAD `fc4495fc9f99cc84675d17d96e5a7e90468901b0`, branch `codex-finalization-megapack-part12`, clean at HEAD before this continuation's local changes; `origin` was fetched and the migration-map source at assistant commit `460e749` was read. The working changes were the in-progress continuation, not unrelated user edits.
- Added `server/employee_identity.py` as the one runtime compatibility adapter. API/service/UI user, assignment, work and payroll contracts use `employee_id`; old table keys and immutable historical payroll snapshots are translated only at this adapter boundary. Existing columns and facts remain in place.
- Routed Excel employee catalog, template, profile updates and creation through the canonical repository/adapter. Shared Web/Android role gates and fixtures now use `employee_id` instead of `telegram_id`.
- Added a real PostgreSQL/RLS integration test using identical retained legacy IDs in two synthetic companies. It checks distinct canonical IDs, canonical API payloads, no cross-company employee listing, and rejection of the foreign employee ID. The test is in the existing disposable Web PostgreSQL workflow; it has not yet executed locally.
- Added the assistant-branch read-only identity audit and classifier tests. Current generated `PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md`: P0 external Telegram/Termux runtime **0**, P0 direct runtime identity dependencies **0**, P1 explicit adapter/import/schema/API-boundary references **50**, P2 history/test/fixture references **129**. P1 source lines and named coverage suites are enumerated in the map.
- At the time of the initial push, readiness counts were **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; the PostgreSQL result was still pending. This was superseded by the verified item-102 checkpoint above.

### TESTS / CHECKS

- `python -m unittest test_portal_app_server test_production test_production_activity test_payroll_settlement test_documents_api -q`: **103 passed, 0 failed**.
- `python -m unittest test_excel_import test_excel_template -q`: **21 passed, 0 failed**.
- `python -m unittest discover -s server -p 'test_*.py' -q`: **268 run, 43 skipped, 0 failed**. Skips include opt-in PostgreSQL/VPS gates.
- `python -m unittest ops.test_employee_identity_migration_audit -q`: **8 passed**; the actual scanner ran with `--fail-on-p0`: P0 **0**.
- `node --test android_src/tests/ui.test.cjs android_src/tests/employee-create-mode.test.cjs android_src/tests/legacy-boundary.test.cjs`: **33 passed, 0 failed**.
- `node --test android_src/tests/web-adapter.test.cjs android_src/tests/web-share.test.cjs android_src/tests/web-smoke.playwright.cjs android_src/tests/build-security.test.cjs`: **10 passed, 0 failed**.
- `python -m compileall -q server ops`, JavaScript syntax checks, and `git diff --check`: passed.
- Local PostgreSQL execution is unavailable (`psql` and Docker commands are absent); the new disposable PG test awaited the branch's Web workflow at this initial snapshot. Its later result is recorded in the superseding checkpoint above.

### NEXT

- Initial next at the time: push, verify Web PostgreSQL and Server, then update item 102 from CI evidence. Completed; see the superseding focused checkpoint above.
- Continue remaining Part12 software tasks; no complete/blocked flag is justified. Production DB/service, DNS, secrets and cutover were not touched.

## LATEST CHECKPOINT — Server regression rerun — 2026-09-30

- Test-only commit `05530ec85decac64675fe8593d3b2d7b6cf4531c` replaces a substring search against serialized audit JSON (where a UUID could coincidentally contain `240`) with exact allowlisted-key assertions for settings and permission audit events. The targeted audit test passed locally; `py_compile` and `git diff --check` passed.
- Web run `36716682510` at `05530ec` passed `web` and `documents-postgresql`; the employee identity PG test ran as part of the passing 30-test disposable suite, with cleanup `db=0 roles=0 temp=0`.
- Server run `36716682521` passed Python 3.11 and 3.13: **268 tests / 42 skipped / 0 failed** on each runtime. The earlier single 3.13 invoice-XLSX idempotency failure at `f7ccb72` was not reproduced; no generation semantics were changed, so record it as a transient CI failure rather than a fixed product defect.
- Focused identity gate remains closed at 75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌; no schema drop, payroll/history rewrite, or removal of the P1 bridge list.
- **Exact NEXT:** proceed with broader Part 12 Client 360/source-backed gap inspection in `android_src/app/src/main/assets/production.js` versus `server/production_service.py`, as recorded in the earlier A–D checkpoint. If no source-backed gap is found, move on to REAL-money inventory/reconciliation and Windows thin client/installer. Keep final Web UI/PG, VPS and release evidence honest; no production DB/service/DNS/cutover without owner approval. No autopilot completion/blocked flag; cutover NOT performed.

## FOCUSED REVALIDATION — canonical employee_id runtime — 2026-09-30

- Starting HEAD `70d9571b56c795dceae609c492262301fa7c92f8` was clean and synced after fetch. This HEAD only adds evidence documentation after the last employee-identity source change; no code or data migration was made in this revalidation.
- Read the assistant-branch migration map at `460e749` and compared it with the current scanner, not blindly cherry-picked. The old map's P0 count is superseded. Current `ops/employee_identity_migration_audit.py --fail-on-p0` reports **P0 0**, with **50 P1** bridges split into 45 explicit compatibility, 1 import/export, 2 legacy-schema, and 2 runtime-compatibility references; **129 P2** history/fixture references. P1 identity history/schema/import bridges remain listed and retained.
- Current local tests: migration-audit suite **8/8**; canonical payroll/legacy-adapter cases **2/2**; full server discovery **268 run, 43 skipped, 0 failed**; `ops.test_infra_readiness` **8/8**; compileall passed. `test_documents_postgresql` discovered 30 tests and skipped all 30 locally because no disposable PostgreSQL DSN/service is configured.
- The canonical identity cross-company API/RLS test was already executed in GitHub disposable PostgreSQL at `05530ec` (Web `36716682510`): the job passed 30 tests (2 skipped), including the employee-ID contract, and teardown evidence was `db=0 roles=0 temp=0`. This is prior CI evidence on unchanged identity source, not a new PG run at documentation-only HEAD `70d9571`.
- Item 102 stays ✅; current readiness totals remain **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. No destructive schema changes, legacy history rewrites, production access, secrets, or Telegram/Termux runtime.
- **Exact NEXT:** inspect Client 360's remaining profile blocks against existing source routes, then perform the legacy money `REAL` inventory and reconcile stored-major-unit APIs against current integer-minor-unit paths. Do not alter or convert existing financial facts without additive migration plus reconciliation evidence. Continue Windows thin client/installer and other remaining software gates afterward. No completion or blocked flag; production cutover not performed.

## SOFTWARE INVENTORY — legacy monetary REAL boundary — 2026-09-30

- Inspected checked-in PostgreSQL DDL, active compatibility writes, the canonical JSON ledger, and reconciliation code. No deployed SQLite schema or financial rows were opened.
- Added `PORTAL_MONEY_REAL_INVENTORY.md`: PostgreSQL compatibility columns are `NUMERIC`; SQLite `REAL` declarations found by source scan are synthetic tests; the canonical service stores money as integer kopecks in JSON payloads and payroll settlement `amount_minor`; compatibility write boundaries still divide integers by 100 into Python floats. The existing migration snapshot comparison detects structural/value drift but does not compare each legacy major-unit fact to its canonical linked kopeck fact.
- Client 360 source/UI review found working source-backed requisites, operation/tariff history, products, batch/task, document, and receivable links in the current flow. This does not close item 17: the roadmap's broader editable-profile acceptance remains partial and no unsupported source field was invented.
- Tests after the inventory artifact: migration validation, migration import and payroll-settlement suites **40 passed, 0 failed**; `compileall` and `git diff --check` passed. Full server discovery immediately before the artifact: **268 run, 43 skipped, 0 failed**.
- No status promotion: readiness stays **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. No database, financial fact, runtime, schema, or deployment was changed.
- **Exact NEXT:** implement a read-only synthetic reconciliation test that ties representative legacy-major-unit amounts to canonical integer-minor-unit facts, including half-cent/rounding boundaries, and proves legacy snapshots remain unchanged; then evaluate a dialect-safe exact dual-write boundary. Do not backfill or convert imported facts without disposable snapshot reconciliation. Continue remaining Client 360 acceptance, Windows client/installer, and release gates. No complete/blocked flag.

## IMPLEMENTED — read-only legacy/canonical money reconciliation — 2026-09-30

- Added `reconcile_linked_work_money()` to `server/migration_validation.py`. It reads only explicit canonical `works.legacy_id` links, constrains both legacy and ledger reads by one company, compares major-unit legacy values to integer minor units with `Decimal`/`ROUND_HALF_UP`, rejects missing/duplicate links, wrong tenant payloads, non-integer canonical amounts, and value drift, and returns counts without exposing values or writing rows.
- Synthetic tests cover duplicate legacy IDs across two companies, unchanged source rows, a half-kopeck boundary (`1.005` → `101`), mismatch rejection, and visibility of unlinked legacy work count. No migration/backfill was run.
- Tests on final implementation: `test_migration_validation`, `test_migration_import`, and `test_payroll_settlement` **42 passed**; compileall and `git diff --check` passed. Full server discovery immediately before the final return-count refinement: **270 run, 43 skipped, 0 failed**; scanner **8/8**, infra readiness **8/8**.
- Local disposable PostgreSQL remains unconfigured; no live PG claim is made for this helper. Roadmap item 105 remains 🟡; totals **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**.
- **Exact NEXT:** review the three float-producing major-unit compatibility writes and design a dialect-safe conversion test, then exercise linked-work reconciliation through a disposable PostgreSQL fixture if that test gate is available. Extend reconciliation only where canonical stable links already exist; do not infer missing history or convert imported balances. Continue Client 360 acceptance, Windows thin client/installer and remaining final gates. No completion/blocked flag; production cutover not performed.

## IMPLEMENTED — dialect-safe legacy money binding — 2026-09-30

- Added `server/money_units.py:legacy_major_currency()`: integer kopecks become exact `Decimal` for PostgreSQL `NUMERIC`; SQLite receives the existing float-compatible binding because imported legacy `REAL/NUMERIC` schemas are variable. Non-integer minor-unit inputs and unknown dialects fail closed.
- Routed work-log rates/salary/revenue and material movement/direct-cost projections through this boundary. Canonical integer-kopek payloads remain authoritative; no old rows or schema were rewritten.
- Tests: Server full discovery **274 run / 43 skipped / 0 failed**; identity audit plus infra readiness **16/16**; targeted money boundary **4/4**; migration/import/payroll **42/42**; compileall/diff check passed.
- At immediately preceding source SHA `3270d44`, GitHub Server Python 3.11/3.13, Web and its disposable PostgreSQL job all passed. The newly changed money binding is not included in those runs; current disposable PostgreSQL test file skips locally without DSN, so fresh CI for the next pushed source SHA remains necessary.
- Item 105 remains 🟡; totals **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. The converter does not remove compatibility REAL affinity or prove deployed rows.
- **Exact NEXT:** commit/push this tested boundary; await Server 3.11/3.13 and Web `documents-postgresql` on the new SHA and diagnose any failure. Then add PostgreSQL adapter-level coverage for Decimal binding plus linked work reconciliation under the existing disposable fixture. Preserve REAL SQLite compatibility and all historical values. Continue broader Client 360, Windows thin client/installer, and final release gates. No complete/blocked flag; no production cutover.

## Focused continuation — disposable PostgreSQL money reconciliation test — 2026-09-30

- Added `test_linked_legacy_and_canonical_money_reconcile_on_postgresql` to the existing isolated Documents PostgreSQL suite. It creates synthetic company-scoped work through the API, invokes the read-only linked-fact reconciliation under the tenant scope, and asserts linked facts and money-field checks without returning monetary values.
- Local evidence before push: `test_money_units`, `test_migration_validation`, `test_migration_import`, `test_payroll_settlement`, and `test_documents_postgresql`: **77 run, 46 passed, 31 skipped, 0 failed**. All skips are PostgreSQL integration cases gated on an isolated DB DSN; they are not considered passes. `python -m compileall -q server` and `git diff --check` passed.
- Previous code checkpoint `059c567` had successful GitHub Server Python 3.11/3.13 and Web/web plus disposable `documents-postgresql` jobs; this new integration test is not in that SHA and awaits its own CI execution.
- Roadmap stays **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**; money item 105 remains 🟡. No production facts or schema changed.

**Exact NEXT:** commit/push this test checkpoint, then verify Web's named `documents-postgresql` job at the resulting SHA. Confirm the job includes the new test and teardown succeeds before updating the report. Keep canonical kopecks authoritative; no data conversion or production reconciliation.

### PostgreSQL reconciliation feedback and correction — 2026-09-30

- The disposable PostgreSQL run at `60f99db` exposed a real contract mismatch: canonical `works` records do not carry `direct_cost`; the canonical source is the sum of company-scoped `usage.cost` rows for that work. The failing gate correctly cleaned up its disposable resources (`db=0 roles=0 temp=0`).
- `ffeba71` added field-name-only diagnostics; Web's `documents-postgresql` run confirmed `direct_cost` was the non-integer/missing canonical field. No amounts or row payloads were emitted.
- The reconciliation now derives legacy `direct_cost` from linked canonical usage rows, validating their company marker and integer-minor `cost`. A synthetic unit test checks exact equality and fails closed when usage drifts. It does not mutate either source.
- Local migration-validation and money-unit tests: **14/14 passed**. The earlier full local Server attempt on this source had **275 run / 44 skipped / 1 failure** in an existing XLSX request-id repeat assertion; rerunning that exact assertion together with migration/money tests passed **15/15**. Treat the full-suite failure as recorded, not a green full run. Server workflows at `ffeba71` passed 3.11 and 3.13; its PostgreSQL run was superseded by this fix.

**Exact NEXT:** commit/push the usage-based reconciliation correction and re-run the disposable PostgreSQL and Server workflows. Update this checkpoint only from those named final-SHA results; retain the money readiness item as 🟡 until the corrected linked-fact gate succeeds.

### Bounded linked-work verification after disposable duplicate finding — 2026-09-30

- The whole-company disposable PostgreSQL run at `f6338d6` reached the linked-money test but failed closed because an earlier synthetic case had duplicate canonical `legacy_id` links. Teardown succeeded (`db=0 roles=0 temp=0`); do not report a full-scan PG pass.
- Kept full-scan duplicate detection strict. Added optional `canonical_work_ids` to the read-only validator so the PG integration can validate exactly the synthetic work just created, while a SQLite contract test proves the unfiltered full scan still rejects duplicate links. The bounded test does not certify all company history or production data.
- Local `test_migration_validation` + `test_money_units`: **15/15 passed**; full local Server suite for the same prior behavior: **276 run, 44 skipped, 0 failed**; compileall and diff check pass. Server 3.11/3.13 passed at `f6338d6`; Web UI passed, but its PG job failed on the duplicate-link finding.
- Money roadmap item remains 🟡 pending the corrected bounded disposable-PG result and, separately, full-history reconciliation. No live data was read or changed.

**Exact NEXT:** push the bounded PG assertion and duplicate-scan regression test. Verify the specific-record test passes on disposable PostgreSQL with fixture cleanup. Preserve a separate explicit note that full-company reconciliation fails on duplicate synthetic history until that integrity condition is investigated; do not suppress duplicates or run production reconciliation.

## Final evidence — linked legacy money check + canonical employee runtime audit — 2026-09-30

### Current source and CI

- Tested source SHA: `35db147` (`test: bound linked money check to synthetic work`); final documentation-only checkpoint is `5e9ff09`, pushed and clean. `git diff --check` and `python -m compileall -q server ops` pass.
- Web run `36722642388` at this SHA passed `web` and `documents-postgresql`. The isolated PG suite ran **31 tests, 2 gated skips**, including `test_linked_legacy_and_canonical_money_reconcile_on_postgresql`; cleanup explicitly verified `db=0 roles=0 temp=0`.
- Server run `36722642200` passed Python 3.11 and 3.13: **277 tests per runtime, 43 skipped, 0 failures**.
- Local full Server discovery before the final optional-filter unit addition: **276 run, 44 skipped, 0 failures**. Current migration/money targeted tests: **15/15**; audit + infra readiness: **16/16**; identity scanner `--fail-on-p0`: P0 **0**. Compileall and diff checks pass.

### Scope/result

- Item 102 remains ✅: P0 external runtime **0**, P0 active direct identity **0**; P1 **50** explicit compatibility/import/schema/runtime bridge refs retained, P2 **129** history/fixture refs. No Telegram/Termux runtime is enabled.
- Item 105 remains 🟡: PostgreSQL compatibility binds exact Decimal major units; read-only linked work reconciliation uses integer-minor canonical facts, including direct cost derived from same-company usage. The fresh, bounded PostgreSQL linked-record case passed and reveals no monetary values.
- A previous unfiltered whole-company reconciliation over the *shared disposable test history* failed closed because duplicate canonical links to a legacy work key existed among earlier synthetic test rows. The corrected bounded test does not claim that all historical links are clean; full-company duplicate investigation and any authorized imported-snapshot rehearsal remain open. The earlier PG job also cleaned all disposable resources.
- Numbered roadmap remains **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**. No readiness item changed status.
- No production DB, service, DNS, cutover, secrets or real financial records were touched.

**Exact NEXT:** inspect the synthetic PostgreSQL suite's earlier work-producing tests and isolate the origin of duplicate canonical legacy links. If caused by fixture/order or an application double-write, correct that software defect with a strict unfiltered PG regression; if they are valid multiple records, define an explicit no-data-loss reconciliation policy and cover it. Do not weaken duplicate detection. Then continue software items 85 (Windows thin client/installer) and 77 (safe marketplace-news scheduler), and final regression/release gates. No complete/blocked flag; Part 12 remains open.

### End-of-turn checkpoint

- The code-tested SHA is `35db147`; following documentation-only commits carry the evidence/NEXT. Branch `codex-finalization-megapack-part12` is pushed and clean at its current tip.
- The `employee_id` focused DoD is met: current audit P0=0 and all 50 P1 bridges remain enumerated/covered; this does not close Part 12. Next work is the duplicate-link origin above, followed by the broader pending software roadmap. No autopilot flag was created.

## Latest verified continuation — Windows, money and news framework — 2026-09-30

- Latest code source: `4a1629cb4b8aa49f5b49d931f9b23e59771be500`; documentation-only commits `0e89f9b` and `f3c14af` are pushed above it. Branch is clean at `f3c14af` before this append.
- Web run `36727892853` passed `web` and disposable `documents-postgresql`; PostgreSQL ran **31 tests, 2 expected skips**, including strict unfiltered money reconciliation, with cleanup `db=0 roles=0 temp=0`. Server `36727892708` passed Python 3.11 and 3.13 (**289 tests each, 43 skips**). Windows `36727892734` passed compile/publish/install. Earlier Windows `36726873659` failed on missing XAML entrypoints; `38e93bd` added them, and subsequent Windows runs passed.
- On current code, local `test_desktop_update test_portal_app_server`: **18/18**; `node --test android_src/tests/*.test.cjs`: **52/52**, including browser UI; `ops.test_infra_readiness`: **8/8**. `compileall`, XAML/project XML parsing, PowerShell installer contracts and `git diff --check` passed.
- Money synthetic duplicate source was corrected in test fixture clones; strict unfiltered disposable-PG full test now passes. No imported or production facts were inspected/converted. Item 105 remains 🟡 pending an authorized disposable imported SQLite snapshot because deployed affinities and rows are unknown.
- News runner is disabled by default; it has explicit injected bounded adapters, no fetcher, no verified official public feed and no installed timer. Items 77–79 remain 🟡.
- Item 85 is 🟡: WPF/WebView2 wrapper, HTTPS/loopback origin boundary, checksum/path-safe current-user installer, CI package and a fail-closed optional manifest API. No signed release or ordinary Windows device verification; update manifest must remain unset until publisher/source policy is trusted.
- Numbered counts: **75 ✅ / 33 🟡 / 6 ⏳ / 12 🔌**. Production DB/service/DNS/cutover/secrets untouched. No autopilot complete/blocked flag.

**Exact NEXT:** priority A: finish the remaining invitation/access/settings/audit permission matrix called out in `PORTAL_RELEASE_READINESS_MATRIX.md` (Owner/Director permissions and combined audit/UI flow) with cross-company negative tests; then targeted Server/Web/disposable-PostgreSQL tests, commit and push. Continue with next software-completable Client 360 / payroll / receivables and Documents gaps before final regression. Latest source is `4a1629c`; latest docs checkpoint was `f3c14af`. Production cutover NOT performed.

## AUTOMATIC CONTINUATION — Client 360 shipment history and receivables PostgreSQL regression — 2026-09-30

- Starting HEAD `23bd46fbe5616b403fc0d76d71a0534ddf42356e` was clean and synced to origin after fetch. Required Knowledge Base, Constitution, roadmap, AGENTS, readiness, report and progress files were reviewed; assistant infrastructure commit `1066c77` remains integrated at `05ab65e`.
- Client 360 item 17 was extended in `664050d`: shared UI now displays client-scoped FBS/FBO shipment and return history from `/api/v3/shipments`; browser tests prove foreign-client/foreign-tenant rows are excluded. UI suite passed 32/32; broader Android/Web Node suite passed 53/53; JS syntax and diff checks passed. This does not close all item-17 acceptance.
- CI at `664050d`: Web, Server 3.11/3.13, Android UI and staging APK passed. No production release occurred.
- The Web disposable PostgreSQL job at `23bd46f` exposed a real compatibility defect: shared historical invoice records may lack `client_id`, while `Production.receivables()` assumed it was always present. The CI test failed with `KeyError: 'client_id'`; teardown verified `db=0 roles=0 temp=0`. The report intentionally ignores unlinked legacy invoices in this client-specific aging view instead of inventing an association. Added a unit regression and a PostgreSQL assertion that returned records belong to the selected client.
- Local validation after the fix: targeted aging boundary/timezone/unlinked-row cases passed; `test_documents_postgresql` discovered 33 tests and skipped because this workstation has no disposable PostgreSQL fixture. Full Server discovery passed **294 tests / 46 skipped / 0 failed**; `ops.test_infra_readiness` passed **8/8**; compileall and `git diff --check` passed. CI validation of the correction is pending.
- Readiness stays **75 ✅ / 33 🟡 / 6 ⏳ / 12 🔌**; no roadmap item was promoted. Production DB/service/DNS/cutover and secrets were untouched.

**Exact NEXT:** commit and push the receivables fix and tests; inspect the resulting SHA's Web `documents-postgresql` and Server 3.11/3.13 checks, requiring both the PG assertion and disposable-resource cleanup to pass. Then continue the A Owner/Director invitation/settings/audit role matrix and remaining B/C/D software items. No completion or blocked flag; production cutover NOT performed.

## VERIFIED — receivables aging PostgreSQL regression — 2026-09-30 (`22ce6f3`)

- Corrected-SHA GitHub checks all passed: Server Python 3.11 and 3.13 each ran 294 tests with 45 gated skips; Web passed its browser tests; `documents-postgresql` ran 33 tests with 2 expected skips, including the legacy missing-client regression and aging role/filter case. Teardown verified `db=0 roles=0 temp=0`.
- Local full Server discovery was 294 tests / 46 skips / 0 failures; targeted receivables cases 3/3; infra readiness 8/8; compileall and diff check passed. Local PostgreSQL cases were skipped, so the disposable CI run is the PG evidence.
- Item 42 is ✅; numbered roadmap counts are now **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. Item 17 remains 🟡; shipment/return history was added in `664050d`, but full profile acceptance is still open.
- Production data/service/DNS/cutover, secrets and phone test execution were not used.

**Exact NEXT:** inspect roadmap item 33 alias/history behavior in `server/production_service.py`, repository schemas and shared Client 360 search. Implement only a missing canonical source-backed alias lifecycle (preserve canonical names/history and company scoping); if no safe source exists, document the missing source and move to another open software task. Run Server/Web/disposable PostgreSQL and UI coverage before any status promotion. Then continue A's remaining verifiable Owner/Director matrix and C/D gaps. No autopilot flag; production cutover NOT performed.

## AUTOMATIC CONTINUATION — employee Excel alias ambiguity guard — 2026-09-30

- Knowledge Base lists eight known employee surname spelling aliases. Added `server/employee_names.py` as a search-key helper and used it only to detect duplicate/ambiguous names in Excel imports when no stable employee ID is supplied. It does not rewrite names, silently bind identities, merge employees, or create a persistent alias record.
- Regression covers all documented aliases, Unicode normalization, punctuation/order/case, rejected ambiguous preview, and unchanged canonical employee name.
- Tests: `python -m unittest test_excel_import -q` **17/17**; full Server discovery **295 tests / 46 skipped / 0 failed**; `python -m compileall -q .` and `git diff --check` passed. CI at the new source SHA is pending. The skipped full-suite tests are fixture/environment gated; local disposable PostgreSQL is not configured.
- Item 33 stays 🟡 and counts remain **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. No complete/blocked flag. Production data/service/DNS/cutover and secrets untouched.

**Exact NEXT:** commit and push the tested alias ambiguity guard and documentation, then verify Server Python 3.11/3.13 and Web disposable PostgreSQL at that SHA. Next inspect actual remaining Owner/Director invitation, company-settings and audit role cases in `server/test_documents_postgresql.py` and shared UI tests; add only a demonstrable missing permission/cross-company case. Preserve all canonical identities and production boundaries.

## AUTOMATIC CONTINUATION — invitation/audit role boundary and redaction regression — 2026-09-30

- Inspection found one missing explicit matrix assertion: a Director must be denied the separate Platform Owner support-audit endpoint while retaining access to the same-company audit after an invitation action. Added the PostgreSQL assertion and a shared browser sequence that filters company audit after Director invite decisions and verifies no platform-audit request is emitted.
- CI for prior source `fd98617` found the disposable PostgreSQL audit-redaction test could fail when the string `240` appeared incidentally in a random UUID/timestamp. This was a test false positive, not a sensitive field leak. The stricter regression now asserts the exact value-free audit row shape (`id`, tenant/actor/event/entity, field names, timestamp) and rejects `values`/`details`; it keeps checking the expected setting field names.
- Current local validation: `node --test android_src/tests/*.test.cjs` **53/53**; `ops.test_infra_readiness` **8/8**; compileall and diff check passed. The previous Web PG failure cleaned up (`db=0 roles=0 temp=0`); local PG tests skip because no local disposable fixture is configured. The corrected PG assertion is pending CI.
- Roadmap counts unchanged **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**; no complete/blocked flag; production untouched.

**Exact NEXT:** commit/push the corrected redaction and Director/company-audit role tests; verify Web `documents-postgresql` and Server 3.11/3.13 at that SHA, including disposable-resource cleanup. If green, record the tested A role boundary, keep production rollout/user-limit configuration open, and proceed to Client 360/item 17 source-backed gaps or batch economics/item 28. No production cutover.

## AUTOMATIC CONTINUATION — batch plan financial permission boundary — 2026-09-30

- Starting HEAD `a70b7f736a58f13f55fe741c15a1e7661caa29dd` was clean and synced after fetch; required Part 12 docs, AGENTS, Knowledge Base and Constitution were read. Assistant infra commit `1066c77` remains integrated.
- Item 28 review found that task creation accepted a nonzero planned `other_cost` with `tasks.manage` alone, despite the shared UI exposing the field only to `finance.read`. The API now requires `finance.read` for a nonzero plan override, while operational task creation with zero/default cost remains available. Android/Web omit the field if it is not rendered.
- Added server unit coverage for manager denial/no task creation and Director success with integer-cent plan data; added opt-in PostgreSQL manager denial/default-zero test and a two-role browser flow checking hidden-field omission. No RLS or existing test was weakened.
- Local validation: targeted production tests **2/2 passed**; full Android/Web Node suite **54/54 passed**; full Server discovery **297 tests, 47 gated skips, 0 failures**; `ops.test_infra_readiness` **8/8**; opt-in `test_documents_postgresql` **34 skipped** (no disposable local PostgreSQL fixture); compileall, JS syntax and `git diff --check` passed. Earlier assertion against manager-visible batch list was invalid because manager role does not list batches; replaced with direct temporary repository state assertion and reran the targeted tests successfully.
- Roadmap item 28 remains 🟡 while broader planned-source coverage is open; counts remain **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. No production resources or secrets were used.

**Exact NEXT:** commit/push the role-gated plan-cost API/UI regression and status docs; verify Server Python 3.11/3.13 and Web `documents-postgresql` against that exact SHA, including disposable resource cleanup. If green, record the narrower role boundary, keep item 28 🟡 for source completeness, then proceed to item 17's remaining Client 360 acceptance. Production rollout/cutover remains untouched; no completion/blocked flag.

## VERIFIED — batch plan financial permission boundary — `968cbe2` — 2026-09-30

- `968cbe2` passed GitHub Server isolation Python 3.11/3.13, Web, disposable PostgreSQL, Android UI and staging APK checks. The PostgreSQL job's test and container teardown steps both succeeded. No production release/cutover ran.
- Local validation on code before the docs-only evidence update: targeted production tests **2/2**; Android/Web Node+Playwright **54/54**; Server discovery **297 tests / 47 skips / 0 failures**; `ops.test_infra_readiness` **8/8**; compileall, JS syntax and diff checks passed. Local PostgreSQL suite was environment-skipped (34 tests); CI supplies the PG evidence.
- Item 28 stays 🟡 because wider plan-entry/source completeness remains open; counts stay **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. No production or secret use.

**Exact NEXT:** continue item 17 Client 360 from its open acceptance: inspect the current client profile UI/API and identify the next concrete, source-backed editable or linked block gap. Preserve tenant scoping and history; add service, browser and opt-in PostgreSQL assertions only for a real missing contract. Do not promote item 17 without full evidence. Part 12 remains open; no completion/blocked flag.

## AUTOMATIC CONTINUATION — Client 360 partial-source error state — 2026-09-30

- Profile inspection found that allowed Client 360 sources used `.catch(()=>null)`, after which failed reads were indistinguishable from empty collections; the card omitted those sections without saying its data was incomplete.
- Shared Android/Web UI now lists the names of allowed source sections that failed and labels the card as partial, while continuing to render source data that did load. Error text is escaped. Added a browser regression that returns a synthetic 503 for shipments and asserts the explicit shipment/return warning alongside available requisites.
- Local validation: focused Client 360 browser UI **34/34**; full Android/Web Node+Playwright suite **55/55**; `ops.test_infra_readiness` **8/8**; JavaScript syntax and `git diff --check` passed. No backend, PostgreSQL, or production data was changed for this UI-only correction.
- Item 17 remains 🟡: broader profile editing acceptance is still unspecified/incomplete. Roadmap counts remain **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. Current SHA CI is pending.

**Exact NEXT:** commit/push this shared UI partial-source state and regression, then verify current-SHA Android UI/build, Web, Server and disposable PostgreSQL checks. If green, continue item 43 profitability by inspecting existing canonical source facts and reconciliation coverage; do not invent/allocate absent amounts or promote item 17/43 without full evidence. No autopilot flag; production cutover remains unperformed.

## AUTOMATIC CONTINUATION — monthly profitability source breakdown — 2026-09-30

- Item 43 review found the API already supplies monthly revenue, payroll, materials, client-attributed expenses, company overhead and profit, but the financial radar displayed only profit and optional overhead. The UI now exposes every existing component, keeps shared overhead separate from client-attributed costs, sorts months newest-first, and states when no confirmed monthly facts exist. No cost allocation or financial source was invented.
- Browser regression uses synthetic amounts and deliberately reversed month order to check component labels and newest-first rendering. Local validation: focused UI **35/35**, full Android/Web Node+Playwright **56/56**, finance service tests **2/2**, `ops.test_infra_readiness` **8/8**, JS syntax and diff checks passed. The opt-in PostgreSQL profitability reconciliation test skipped locally because no disposable DB is configured.
- Roadmap item 43 remains 🟡 pending remaining source/role acceptance and current-SHA CI; counts remain **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. No production systems touched.

**Exact NEXT:** commit/push monthly profitability UI coverage and evidence; verify current-SHA Android UI/APK and Web disposable PostgreSQL (plus all triggered gates) and cleanup. Then continue next source-backed gap in priority order—payroll role/PostgreSQL coverage or Documents cross-session parity—without claiming the production-dependent items complete.

## AUTOMATIC CONTINUATION — payroll settlement manager/accountant role coverage — 2026-09-30

- Existing unit tests covered accountant payouts and manager denial, but the disposable PostgreSQL E2E only exercised packer denial and admin payout. Extended that E2E to prove a manager cannot append a payout and an accountant can append a second payout; the exact PostgreSQL totals become 400 accrued / 150 paid / 250 balance, both entries remain bigint minor units, and the closed snapshot is unchanged.
- Extended the shared UI role-flow test: accountant sees and uses the payout action; manager remains read-only. No settlement ledger or authorization rule was weakened.
- Local tests: `test_payroll_settlement` **25/25**; Playwright browser UI **35/35**; infra readiness **8/8**; compileall, JS syntax and diff check passed. Current test_documents_postgresql suite requires the CI disposable PostgreSQL service and will be verified after push. The previous `cc502e9` Android UI, APK and Web checks succeeded; this new extension is pending CI.
- Roadmap item 38 remains 🟡 until expanded PG evidence and rollout; counts remain **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**.

**Exact NEXT:** commit/push the payroll role E2E and UI regression plus evidence; verify Web `documents-postgresql` on that SHA, Server checks and all triggered Android gates. Confirm job teardown succeeds. Then inspect the remaining high-priority Documents cross-session/UI or payroll source-backed gap and update exact NEXT.

## VERIFIED — payroll settlement + exact profitability — `42dd31f` — 2026-09-30

- GitHub Web run `36770988439` passed; disposable PostgreSQL ran **34 tests / 2 gated skips / 0 failures**. Both `test_payroll_settlement_role_scope_and_closed_snapshot_over_postgresql` and `test_zz_profitability_reconciles_postgresql_source_facts_without_allocating_overhead` passed. Cleanup verified `db=0 roles=0 temp=0`.
- GitHub Server run `36770988418` passed on `42dd31f`. Runtime source at `d98f501` adds exact client/company margin basis points and finance totals while retaining kopeck money facts; PostgreSQL role accounts in the test fixture are created through the canonical company-scoped user path.
- Item 38 is now ✅: accrued/paid/balance, append-only payouts, accountant/admin allowance, manager/packer denial, cross-company denial, replay safety and closed-snapshot immutability are evidenced.
- Item 43 is now ✅: client/batch/company revenue, payroll, materials, attributable expenses, separate company overhead, profit and exact basis-point margins are source-backed and reconciled; no synthetic overhead allocation is introduced.
- Current roadmap counts: **78 ✅ / 30 🟡 / 6 ⏳ / 12 🔌**. Production DB, DNS, release secrets and cutover remain untouched.

**Exact NEXT:** finish item 17 Client 360 by wiring the existing client operation/tariff management path directly from the client card if the existing server capability supports it, with role/UI regression and no duplicate business logic. Then continue only remaining software-completable items; keep domain, physical-device checks, off-server backup target, signed Windows publication, official news sources and production cutover as external owner/provider gates.

## VERIFIED - Client 360 operation and tariff actions - `4ed5ce8` - 2026-09-30

- Client profile now exposes the existing client operation editor only when the catalogue capability is present, and the existing append-only tariff version form only when `rates.employee` or `rates.client` is granted. A tariff created from the profile returns to the same Client 360 card; the restricted-role regression verifies both controls are absent.
- Local full Android/Web Node+Playwright suite: **56/56 passed**; JavaScript parse checks and `git diff --check` passed.
- GitHub Web run `36772536623` passed browser/static checks and disposable PostgreSQL. The PG job passed **34 tests / 2 gated skips** and teardown verified `db=0 roles=0 temp=0`. Android UI run `36772536669` and staging APK run `36772536563` passed. Server 3.11/3.13 remained green at unchanged server source SHA `42dd31f`.
- Item 17 remains 🟡 because its broader client profile and linked-data acceptance is not fully closed. Counts remain **78 ✅ / 30 🟡 / 6 ⏳ / 12 🔌**. No production systems or secrets were used.

**Exact NEXT:** inspect the existing Today service/UI contract against roadmap item 44. The service returns monthly work volume and closed-period payroll totals, but verify whether the shared management dashboard renders both. If absent, add capability-gated metrics and no-closed-period state with service/API/browser/disposable PostgreSQL regressions, without showing payroll fields to roles lacking payroll visibility. Then continue the remaining radar/productivity/reminder software checks; leave external rollout gates open.

## VERIFIED — Client 360 operation/tariff management — `4ed5ce8` — 2026-09-30

- Client 360 now reuses the existing operation-management and historical-tariff flows directly from the client card. Authorized users can open operation CRUD and create a new effective-date tariff for a displayed operation; tariff save returns to the same Client 360 card. No second business-logic path was introduced.
- Restricted users without `clients.manage` / rate capabilities do not receive the management controls. Existing source sections, linked Documents/receivables, shipment/return history and explicit partial-source warning remain intact.
- Local shared UI regression: **35/35 passed**. GitHub at `4ed5ce8`: Web **SUCCESS**, disposable PostgreSQL **SUCCESS**, Android UI **SUCCESS**, APK **SUCCESS**.
- Roadmap item 17 is now ✅. Counts: **79 ✅ / 29 🟡 / 6 ⏳ / 12 🔌**. No production systems or data were changed.

**Exact NEXT:** continue item 46 productivity. Use only existing timed work sources; replace raw IDs in UI where canonical names are available, surface consistency/variability honestly, and prove management vs self-only role scope. Do not invent quality scores when defects are not recorded.
## AUTOMATIC CONTINUATION — source-backed productivity breakdown — `231e3c6` — 2026-09-30

- Analytics now returns canonical employee/client/operation labels alongside stable IDs, groups work by employee/client/product/operation and adds a batch/operation breakdown. The UI uses those labels, shows timed quantity and rate variability only when at least two timed samples exist, and reports unavailable time/quality where the source has no facts.
- Scope tests prove manager team analytics is limited to assigned clients and employee analytics remains self-only. Disposable PostgreSQL E2E checks team/self/foreign-company scope and batch metrics. No quality score or defect count is invented.
- Local validation: `test_production` **51/51**, Android/Web Node+Playwright **35/35**, `ops.test_infra_readiness` **8/8**, Python compileall, JS syntax and `git diff --check` passed. Current-SHA GitHub Server 3.11/3.13, Web, `documents-postgresql`, Android UI and APK all succeeded; PostgreSQL test and container-stop steps passed. Local disposable PostgreSQL is not configured.
- Item 46 remains 🟡 because the work source currently records no defects; quality cannot be measured until real defect facts are captured. Numbered roadmap counts remain **79 ✅ / 29 🟡 / 6 ⏳ / 12 🔌**. No production system was used.

**Exact NEXT:** continue item 47 reminder scheduler. Review the existing disabled-by-default operator runner and persistent cadence/retry/idempotency tests; implement only the remaining safe software gap (a deterministic trusted timer/deployment artifact or operable run contract), and keep activation disabled unless explicitly configured. Then continue the still-partial Documents and access/settings role matrices. No complete/blocked flag is warranted.

## VERIFIED — PORTAL Сегодня + Documents parity — `414a101` — 2026-09-30

- Shared management dashboard now renders source-backed month work volume and capability-gated closed-period paid/balance in addition to existing day/month finance, debt, plan availability and productivity. When payroll visibility is absent the block is not rendered. Local shared UI regression passed 57/57; GitHub Web, Android UI and staging APK at `414a101` all succeeded.
- Documents cross-session/history acceptance is now complete at software level: independent same-company sessions already proved create/list/metadata/download/archive on disposable PostgreSQL with tenant denial and cleanup; the shared UI exposes version/status plus «История версий», with regression for ordered revisions, archived/current labels and denied history access.
- Roadmap items 44 and 68 are now ✅. Numbered counts: **81 ✅ / 27 🟡 / 6 ⏳ / 12 🔌**. Production rollout and physical-device checks remain tracked in their separate items and were not performed here.

**Exact NEXT:** verify current tariff-role PostgreSQL CI at `5702b79` and manager admin-denial CI at `63a1f77`. If green, record those narrower role-matrix improvements without promoting still-external rollout gates; then continue only software-completable partials.

## VERIFIED — financial radar + payroll capability UI — `fa680cd` — 2026-10-01

- Director/admin dashboard payroll summary is capability-gated in both live and preview renderers: it appears only with `payroll.settlement.read` or `payroll.all`, shows accrued/paid/balance from the backend snapshot, and stays hidden after the capability is removed. Stage 3 navigation assertions now await the actual dashboard rerender, eliminating the prior full-suite race without weakening the checks.
- Financial radar now combines only source-backed facts: profitability/months from `finance`, loss-client count from client profit, receivables/overdue only when `invoices.read` is present, and financial-only attention entries from `today`. It does not call receivables without permission and does not invent cost allocation.
- Local merged validation: shared Android/Web UI **57/57**, infra readiness **8/8**, JS syntax and diff checks passed. GitHub at `fa680cd`: Web + disposable PostgreSQL run **153 SUCCESS**, Android UI run **76 SUCCESS**, APK run **90 SUCCESS**. Server isolation run **160 SUCCESS** at parent `0c9674c` covers the unchanged backend and the date-boundary regression fix.
- Roadmap item 45 is now ✅. Numbered counts: **82 ✅ / 26 🟡 / 6 ⏳ / 12 🔌**. Production cutover was not performed.

**Exact NEXT:** inspect item 19 effective-date tariff policy after `5702b79` plus successful descendant Server/Web CI. If no concrete software gap remains, record it as complete; otherwise add only the missing symmetric capability/tenant case. Then continue the remaining software-verifiable access/settings/audit partials without touching production-only gates.

## VERIFIED — effective-date tariff policy matrix — `a80d3a3` — 2026-10-01

- Inspection exposed a real response-redaction bug: tariff POST reused work redaction and could reveal inherited `employee_rate` to an actor holding `rates.client` plus `payroll.own`. The work path keeps its existing payroll visibility semantics; tariff responses now use tariff-specific capabilities only.
- Tariff create and idempotent replay now expose `employee_rate` only with `rates.employee` and `client_rate` only with `rates.client`. The symmetric tests prove both read-history redaction and write denial/allow paths, while preserving duplicate-effective-time rejection and immutable historical work snapshots.
- Local `test_production`: **51/51** passed. GitHub Server run **161**: Python 3.11 and 3.13 each **300 tests / 47 skipped / 0 failed**. Web/disposable PostgreSQL run **154**: **35 tests / 2 expected skips**, cleanup verified **db=0 roles=0 temp=0**.
- Roadmap item 19 is now ✅. Numbered counts: **83 ✅ / 25 🟡 / 6 ⏳ / 12 🔌**. Production cutover was not performed.

**Exact NEXT:** reconcile A items 10–12 and 15 against current evidence. Owner subscription/demo/state/seat/module controls and Director settings are already implemented/tested, so identify only a concrete missing role/policy case; do not keep stale blockers merely for production rollout, which is tracked separately.

## VERIFIED — access/settings/audit matrix reconciliation — 2026-10-01

- Roadmap items 10–11 are software-complete: invitation tokens are hash-only at rest and one-time; expiry/revoke/idempotent replay and tenant isolation are proven; Manager/Packer cannot administer invites; Director can create/approve/revoke in-company; Admin lifecycle is covered; Platform Owner requires explicit company scope; existing employees are linked without duplicate employee creation; accept UI keeps PIN/token out of URLs.
- Item 12 is software-complete for the approved controls: active-seat/concurrency enforcement, standard user limit, unlimited PORTAL, Director capability-gated company schedule/activity settings, Manager/Packer and forged-company denial, plus Platform Owner fee/demo/company-state/service-state/seat/module controls with persistence, validation and audit.
- Item 15 is software-complete: company audit and separate Platform Owner support-audit have actor/event/entity/date filters and pagination; role/tenant boundaries and value-free audit redaction are verified.
- Evidence is cumulative and re-executed by current descendants: shared Android/Web UI run **76** at `fa680cd`; Web/disposable PostgreSQL run **154** at `a80d3a3` (**35 tests / 2 skips**, cleanup **db=0 roles=0 temp=0**); Server run **161** at `a80d3a3` (**300 tests / 47 skips / 0 failed** on Python 3.11 and 3.13).
- Roadmap items 10, 11, 12 and 15 are now ✅. Numbered counts: **87 ✅ / 21 🟡 / 6 ⏳ / 12 🔌**. Production cutover remains separate and was not performed.

**Exact NEXT:** inspect remaining partial item 28 (batch plan/fact economics) for a concrete source-backed gap. Do not promote item 46 quality while no defect source exists; do not enable reminder/news production timers or any cutover gate.

## VERIFIED — batch plan/fact source completeness — 2026-10-01

- Batch planning is fully source-backed: planned payroll and revenue come from the effective tariff snapshot; planned materials come from active operation norms using Decimal quantities and integer minor-unit cost rounding; planned other cost exists only as an explicit finance-gated override.
- Fact economics uses immutable work money snapshots, actual material usage linked to work, and actual batch expenses. Deviation, exact basis-point margins, finished-unit cost and profit per unit are derived from those facts. Missing plan rows remain null/«Недоступно», never an invented zero plan.
- Security/UI evidence already executes on current descendants: finance-gated other-cost entry, denial without capability, tenant denial, browser labels, absent-plan rendering and PostgreSQL plan/fact reconciliation. Server run **161**, Web/disposable PostgreSQL run **154**, and Android UI run **76** are green.
- Roadmap item 28 is now ✅. Numbered counts: **88 ✅ / 20 🟡 / 6 ⏳ / 12 🔌**. No new planning source was invented; production cutover was not performed.

**Exact NEXT:** enumerate the remaining 🟡 roadmap items and classify each as (a) software-completable now, (b) physical-device/manual gate, or (c) external/provider/production gate. Continue only category (a) automatically.
