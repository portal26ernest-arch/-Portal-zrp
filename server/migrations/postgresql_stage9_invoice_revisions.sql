-- Additive readiness marker for the append-only invoice revision workflow.
-- The workflow writes invoice_revisions as new portal_production records and keeps
-- work, invoices, payments, payroll, and closed snapshots immutable.
BEGIN;
INSERT INTO portal_production_migrations(company_id,version,applied_at)
SELECT id,9,CURRENT_TIMESTAMP::text FROM companies
ON CONFLICT(company_id,version) DO NOTHING;
COMMIT;
