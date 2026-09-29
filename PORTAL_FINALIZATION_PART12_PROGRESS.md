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
