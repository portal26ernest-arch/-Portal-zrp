# PORTAL release readiness matrix — Part 12 checkpoint

Statuses reflect the current roadmap and prior verified reports. `✅` means evidenced completion in the named baseline report/test; it does not mean production cutover is approved. This checkpoint did not promote any roadmap status.

| Roadmap item | Feature | Status | Evidence commit/test | Remaining blocker | Owner action required |
|---:|---|:---:|---|---|:---:|
| 2 | Server and PostgreSQL tenant isolation | ✅ | Part 8 report; Part 10/11 real PostgreSQL E2E | Continue release regression | No |
| 10–11 | Invitations and access requests | 🟡 | `0006547`, `b6b4092`, `a8bfcdc`, `c09e44a`; server lifecycle API tests; Playwright covers one-time create/token, manager denial, approve and revoke | Disposable PostgreSQL invite/RLS role rehearsal and broader existing/new employee matrix | No |
| 12 | Company settings and user limits | 🟡 | `0006547`; `test_portal_tenancy` 15/15; owner UI, active-count API, server seat/concurrency tests; Server #42/Web #15 green | Verify owner/director UI in Playwright; confirm module-toggle support/model | No |
| 15 | Administrative audit UI | 🟡 | `0006547`, `cec4536`, `aa5cc64`, `2ca0ad0`, `1f3adc5`; company API filters/scope test and Platform Owner audit surface/filter Playwright flow (UI 22/22) | Owner audit PostgreSQL/RLS integration and company policy matrix | No |
| 17 | Client 360 | 🟡 | `9bf3769`; Playwright Client 360 fixture; permission-aware source-backed detail view | Complete editable blocks, documents drilldown and API role/E2E checks | No |
| 19 | Effective-date tariff history | 🟡 | `0d477bf`, `9bf3769`; history service test/shared UI; Server #45 and Web #19 green | Overlap/conflict and historical-work proofs; write role matrix | No |
| 28 | Batch plan/fact economics | 🟡 | Batch/economy API in `server/production_service.py` | Verify complete plan/fact inputs and UI | No |
| 32 | Managed FBS/FBO/returns | 🟡 | Shipment/batch API exists | Complete workflow states, assignment, return and idempotent UI | No |
| 33 | Name normalization/history | 🟡 | Roadmap only | Alias/rename history migration and tests | No |
| 35 | Product catalog UI | 🟡 | Catalog API baseline | Complete CRUD/archive/search and associations | No |
| 38 | Payroll accrued/paid/balance | 🟡 | `0770275`, `320b6d9`; `server.test_payroll_settlement` 25/25; Web admin-payout/read-only-manager flow; payroll XLSX payment sheet test | Disposable PostgreSQL settlement/RLS E2E remains unrun | No |
| 42 | Receivables aging/overdue | 🟡 | `26e595d`; cents-based aging boundary/partial-payment/pagination test and browser filters; Server #45/Web #19 green | Disposable PostgreSQL integration and broader role/filter proof | No |
| 43 | Profitability | 🟡 | Finance/economy API in production service | Validate unified client/batch/company calculations and UI | No |
| 44–45 | PORTAL Сегодня/financial radar | 🟡 | `today()` in production service | Complete required source-backed metrics and honest empty states | No |
| 46 | Productivity | 🟡 | Work records and analytics API | Unit/hour/quality period comparisons where source data exists | No |
| 47 | Scheduled reminders | ⏳ | `af29605`; `server/test_reminder_jobs.py` 5/5 covers disabled default, tenant argument validation, cadence/offset, deduplication and retry after failure | Still needs source-backed invoice/unbilled-work candidate queries, persistent run/attention sink and operator timer wiring; PostgreSQL/retry integration | No |
| 52 | Payroll XLSX payments sheet | ✅ | `server/test_report_xlsx.py`; `PayrollSettlementTest.test_payroll_xlsx_document_includes_settlement_sheet_and_payment_date` | None for the tested generation flow | No |
| 53,55–56,68 | Documents UI and cross-client sync | 🟡 | `490be25` same-company two-session E2E test added; `e85078e` shared UI virtual folders/current-vs-archive labels; Web #20 green | Run two-session create/list/download/archive and cross-company denial on disposable PostgreSQL; complete history/revision parity | No |
| 59–63 | Android/Web save/share/email | 🟡 | `6137328`; `web-share.test.cjs` 5/5 share/cancel/unsupported fallback/object URL/MIME checks; `native-shell.test.cjs` Android source contracts | Final CI rerun for follow-up and physical native chooser detail remain | Yes (device check only) |
| 77–79 | Marketplace news ingestion | 🟡 | Part 5 trusted boundary and read API | No proven public official source; scheduler/operator framework incomplete | Yes (source only if available) |
| 80–83 | Android app/update/release | 🟡 | `PORTAL_RELEASE_3_4_CANDIDATE_REPORT.md`, CI run 24 | CI build 3.5; protected prod release secrets/approval; user device check | Yes |
| 84 | Functional Web client | ✅ | Parts 8,10,11 reports; Part 10 real role matrix | No new functional blocker for verified scenarios | No |
| 86 | Shared UI and platform parity | 🟡 | Part 10 real Web role matrix and shared-client baseline | Physical Android user check remains manual | Yes (device check only) |
| 85 | Windows installer/update | ⏳ | No Windows client/toolchain in checkout; `dotnet` unavailable locally | Implement thin client, installer and CI artifact | No |
| 93 | Off-server backup | 🟡 | `05ab65e`, `aa94fa3`; provider-neutral pg_dump/hash/manifest/encryption/retention helper and disposable restore hard guard; ops tests 7/7 | External target/provider configuration and isolated PostgreSQL restore rehearsal | Yes (target) |
| 94–95 | Production domain/HTTPS | ⏳ | `05ab65e` nginx HTTPS/loopback template; Stage 7 report: temporary tunnel only; HTTP-01 TCP/80 issue | Domain/DNS/network and production certificate rollout | Yes |
| 96–99 | Final import and production cutover | ⏳ | `PORTAL_PRODUCTION_CUTOVER_RUNBOOK.md` prepared only | Owner approval, freeze, snapshot, reconciliation and controlled cutover | Yes |
| 100 | Rollback design | ✅ | `PORTAL_MASTER_ROADMAP.md`; Stage 7 rollback rehearsal | Final production rollback rehearsal is gated on cutover approval | Yes |
| 102 | employee_id compatibility boundary | 🟡 | Legacy-boundary tests and runtime audit still required | Complete runtime audit; retain historical columns | No |
| 105 | Money normalization | 🟡 | Payroll settlement uses integer minor units; legacy REAL inventory incomplete | Inventory/dual-read reconciliation and disposable PostgreSQL rehearsal | No |
| 106–117 | TalAnt/WMS integration | 🔌 | No official API/sandbox evidence provided | Official API, sandbox and credentials | Yes |

See `PORTAL_FINAL_EXTERNAL_BLOCKERS.md` for only external/provider actions. The Part 12 final report will replace this checkpoint matrix with the final evidence and test run IDs when work completes.

Latest tested source SHA: `1f3adc5`; Android UI #34 and APK #48 passed on this SHA. Server #49 / `36649752281` and Web #26 / `36649752347` passed at parent `5df9dc0` (latest intervening change is a UI-only test). Server matrix ran **218 tests, 19 skipped, 0 failed** on both Python 3.11 and 3.13; all Node tests passed 42/42 at `5df9dc0`, and UI suite passed 22/22 at `1f3adc5`. Latest artifact: `PORTAL_Android_3.5-dev_staging_a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; APK SHA-256 `a9b54f2b65b44ac806d4d46e995676f34200501a387df52f16bfe505197d928e`; archive digest `sha256:cdae0e6c93bbe0d714c73a4f41e2fd910c7819bb9a75906073a367e00d0b38c8`. `05ab65e` integrates infrastructure commit `1066c77`; `aa94fa3` suppresses arbitrary restore-validation output and rejects unsafe backup filename prefixes. No roadmap status was promoted. No Part 12 disposable PostgreSQL/VPS rehearsal or backup restore was run; existing cross-session Documents E2E remains opt-in and unexecuted.
