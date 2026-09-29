# PORTAL — Codex Part 9 report

## Scope

Branch: `codex-invoice-documents-part9`
Base: `4e0d7ce`
Implementation commit: `c4931c8156dbf57ef67214aec623104176c9cb48`

Part 9 closes the remaining invoice/document work without changing release 3.4, signing, CI, deployment, version files, production/VPS data, secrets, or `PORTAL_MASTER_ROADMAP.md`.

## Implemented

- Added real deterministic `invoice_xlsx` generation through the existing `/api/v3/document-generate` route.
- Invoice XLSX uses the current immutable invoice snapshot plus existing company/client requisites, validates required fields and financial arithmetic, and is printable A4.
- Added real deterministic `payroll_slip_xlsx` generation from a CLOSED payroll-period snapshot only.
- Payroll slip is intentionally short: company, period/year, employee, final amount, date, then signatures in the required order.
- Added finalized → editing → finalized invoice revision workflow with append-only revision records.
- Only admin/director can send a company invoice to editing; manager can save a revision only while the invoice is editing.
- Revision editing can change selected original lines, quantity and client price inside the new invoice snapshot without rewriting source work or payroll facts.
- Existing payments fail closed if a revision attempts to change financial rows or total.
- Payments are blocked while an invoice is in editing.
- Existing generated invoice/payroll documents remain immutable; a changed invoice snapshot generates a new document, while unchanged generation is idempotent.
- Added Android/Web UI hooks for invoice XLSX, send-to-editing, manager revision form, revision/state labels, and payroll-slip XLSX.
## Main files

- `server/financial_xlsx.py`
- `server/documents_api.py`
- `server/document_domain.py`
- `server/production_service.py`
- `server/production_repository.py`
- `server/production_migrations.py`
- `server/migrations/postgresql_stage9_invoice_revisions.sql`
- `server/test_documents_api.py`
- `server/test_documents_postgresql.py`
- `server/test_postgresql_invoice_revisions_schema.py`
- `android_src/app/src/main/assets/production.js`
- `android_src/tests/documents-excel.test.cjs`
- `server/requirements.txt`

## Verification

Focused Documents API suite: **12/12 passed**.
Full server suite: **203 total: 184 passed, 19 skipped, 0 failed**.
Android/Node suite: **23 passed, 1 skipped, 0 failed**.
`python -m compileall -q server`: **OK**.
`node --check android_src/app/src/main/assets/production.js`: **OK**.
`git diff --check`: **OK**.

The focused tests cover invoice revision permissions, tenant isolation, payment lock, immutable work facts, XLSX validity/A4 settings, closed payroll snapshots, document metadata, and repeated-generation idempotency.
## Skipped / remaining external validation

- One real-PDF renderer test was skipped because ReportLab is not installed in the local test environment. Runtime dependency remains pinned in `server/requirements.txt`.
- PostgreSQL/VPS integration cases requiring disposable isolated databases were skipped locally. Their schema contract tests passed; this Part 9 branch was not deployed to VPS by design.
- The browser UI regression case was skipped because Playwright is not installed in this worktree environment.
- The Samsung phone disappeared from ADB during the parallel release-3.4 device verification. No post-Part-9 physical-device run is claimed here.

These are environment-dependent validation gaps, not test failures. They must remain visible until the corresponding isolated environments/device are available.

## Safety boundary

No merge, rebase, push, production deployment, VPS data mutation, signing-key access, APK version change, release workflow change, or roadmap edit was performed as part of Part 9.

## Commits

Implementation: `c4931c8156dbf57ef67214aec623104176c9cb48`
Report: this report is committed separately after the implementation commit.
