# PORTAL release readiness matrix — Part 12 checkpoint

Statuses reflect the current roadmap and prior verified reports. `✅` means evidenced completion in the named baseline report/test; it does not mean production cutover is approved. This checkpoint did not promote any roadmap status.

| Roadmap item | Feature | Status | Evidence commit/test | Remaining blocker | Owner action required |
|---:|---|:---:|---|---|:---:|
| 2 | Server and PostgreSQL tenant isolation | ✅ | Part 8 report; Part 10/11 real PostgreSQL E2E | Continue release regression | No |
| 10–11 | Invitations and access requests | 🟡 | Roadmap records table/foundation only | Full invite/approve/revoke UI/API flow and tests | No |
| 12 | Company settings and user limits | 🟡 | `server/test_portal_tenancy.py` company limit/override cases | Complete user-facing settings and Web role matrix | No |
| 15 | Administrative audit UI | 🟡 | `server/portal_tenancy.py`; `server/test_portal_tenancy.py` append-only/owner audit tests | Company audit filters/pagination and Web UI | No |
| 17 | Client 360 | 🟡 | Current roadmap; client/finance APIs | Complete editable blocks and unified client view | No |
| 19 | Effective-date tariff history | 🟡 | Current tariff API and roadmap evidence | Complete history UI/conflict coverage | No |
| 28 | Batch plan/fact economics | 🟡 | Batch/economy API in `server/production_service.py` | Verify complete plan/fact inputs and UI | No |
| 32 | Managed FBS/FBO/returns | 🟡 | Shipment/batch API exists | Complete workflow states, assignment, return and idempotent UI | No |
| 33 | Name normalization/history | 🟡 | Roadmap only | Alias/rename history migration and tests | No |
| 35 | Product catalog UI | 🟡 | Catalog API baseline | Complete CRUD/archive/search and associations | No |
| 38 | Payroll accrued/paid/balance | 🟡 | `server/test_payroll_settlement.py` | Payroll payment UI/export integration remains incomplete | No |
| 42 | Receivables aging/overdue | 🟡 | Invoice/payment API; today attention check in production service | Aging buckets, client totals, filters and tests | No |
| 43 | Profitability | 🟡 | Finance/economy API in production service | Validate unified client/batch/company calculations and UI | No |
| 44–45 | PORTAL Сегодня/financial radar | 🟡 | `today()` in production service | Complete required source-backed metrics and honest empty states | No |
| 46 | Productivity | 🟡 | Work records and analytics API | Unit/hour/quality period comparisons where source data exists | No |
| 47 | Scheduled reminders | ⏳ | No scheduler framework evidenced | Implement idempotent company-scoped jobs and tests | No |
| 52 | Payroll XLSX payments sheet | ✅ | `server/test_report_xlsx.py`; `PayrollSettlementTest.test_payroll_xlsx_document_includes_settlement_sheet_and_payment_date` | None for the tested generation flow | No |
| 53,55–56,68 | Documents UI and cross-client sync | 🟡 | Parts 8/10/11; `PORTAL_PART11_WEB_TEMPLATE_DOWNLOAD_REPORT.md` | Cross-client create/list/download/archive E2E across sessions | No |
| 59–63 | Android/Web save/share/email | 🟡 | Android source contracts and Part 11 browser tests | Complete Web Share browser matrix; device check remains manual | Yes (device check only) |
| 77–79 | Marketplace news ingestion | 🟡 | Part 5 trusted boundary and read API | No proven public official source; scheduler/operator framework incomplete | Yes (source only if available) |
| 80–83 | Android app/update/release | 🟡 | `PORTAL_RELEASE_3_4_CANDIDATE_REPORT.md`, CI run 24 | CI build 3.5; protected prod release secrets/approval; user device check | Yes |
| 84 | Functional Web client | ✅ | Parts 8,10,11 reports; Part 10 real role matrix | No new functional blocker for verified scenarios | No |
| 86 | Shared UI and platform parity | 🟡 | Part 10 real Web role matrix and shared-client baseline | Physical Android user check remains manual | Yes (device check only) |
| 85 | Windows installer/update | ⏳ | No Windows client/toolchain in checkout; `dotnet` unavailable locally | Implement thin client, installer and CI artifact | No |
| 93 | Off-server backup | 🟡 | Existing PostgreSQL backup/restore rehearsal | Provider-neutral tooling and actual external target verification | Yes (target) |
| 94–95 | Production domain/HTTPS | ⏳ | Stage 7 report: temporary tunnel only; HTTP-01 TCP/80 issue | Domain/DNS/network and production HTTPS | Yes |
| 96–99 | Final import and production cutover | ⏳ | `PORTAL_PRODUCTION_CUTOVER_RUNBOOK.md` prepared only | Owner approval, freeze, snapshot, reconciliation and controlled cutover | Yes |
| 100 | Rollback design | ✅ | `PORTAL_MASTER_ROADMAP.md`; Stage 7 rollback rehearsal | Final production rollback rehearsal is gated on cutover approval | Yes |
| 102 | employee_id compatibility boundary | 🟡 | Legacy-boundary tests and runtime audit still required | Complete runtime audit; retain historical columns | No |
| 105 | Money normalization | 🟡 | Payroll settlement uses integer minor units; legacy REAL inventory incomplete | Inventory/dual-read reconciliation and disposable PostgreSQL rehearsal | No |
| 106–117 | TalAnt/WMS integration | 🔌 | No official API/sandbox evidence provided | Official API, sandbox and credentials | Yes |

See `PORTAL_FINAL_EXTERNAL_BLOCKERS.md` for only external/provider actions. The Part 12 final report will replace this checkpoint matrix with the final evidence and test run IDs when work completes.
