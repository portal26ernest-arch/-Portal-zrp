# PORTAL legacy monetary REAL inventory

Read-only source inventory. No production database, imported customer facts, or live environment was inspected. `REAL` declarations below are test fixtures and must not be mistaken for an inventory of deployed rows.

## Findings

| Boundary | Source evidence | Classification | Current behavior |
|---|---|---|---|
| PostgreSQL legacy compatibility schema | `server/migrations/postgresql_core_stage4b.sql`: `portal_client_operations.employee_rate/client_rate`; `work_log.rate/salary/client_rate/revenue/direct_cost`; `payroll_transactions.amount`; `client_invoices.amount_due`; `client_payments.amount`; `materials.unit_cost`; `material_movements.unit_cost` | Financial columns are `NUMERIC`, not `REAL`; `quantity`, stock, and norms are also `NUMERIC` but are not money | Kept as the legacy major-unit compatibility schema. Server statements convert canonical kopecks to major units at the adapter boundary.
| SQLite fixture schemas | `server/test_portal_app_server.py`, `server/test_migration_validation.py`, `server/test_migration_import.py`, and `server/test_portal_tenancy.py` declare representative legacy financial columns as `REAL` | Test-only evidence | Fixtures prove compatibility and preservation behavior; they do not establish the type or values of any real imported SQLite database.
| Canonical production ledger | `server/production_migrations.py` and `server/production_repository.py`: `portal_production.payload` is JSON text; `server/production_service.py:cents` converts major-unit API input to integer kopecks | Canonical application payloads represent money in integer minor units; SQL payload column itself is text | Plans, work snapshots, invoices, payments, expenses, and finance facts use integer kopecks in the new service path. Payroll settlement has a dedicated integer `amount_minor` column.
| Compatibility writes | `server/employee_identity.py:write_legacy_work`; `server/production_repository.py:Repository.consume` and `Repository.project_cost` | Active dual-write boundary; conversion uses Python `/ 100`, which yields a float | Writes old work/rate/revenue/material-cost fields in major currency units. This is a precision-sensitive conversion boundary requiring focused exactness/reconciliation tests before changing or removing it.
| Baseline tariff migration | `server/production_migrations.py:migrate` | Explicit migration from legacy catalog rates to a new baseline | Converts with `Decimal(str(value)) * 100` and `ROUND_HALF_UP`; does not rewrite historical work, invoices, payments, or payroll records.
| Existing cutover comparison | `server/migration_validation.py:snapshot/compare` | Read-only, company-scoped structural/value preservation | Hashes normalized source/destination values and fails closed on schema/row/value drift. It does not yet reconcile each legacy major-unit financial field against a linked canonical integer-minor-unit fact.

## Scope limits and follow-up

- Static source search found no production server DDL declaring financial columns `REAL`; PostgreSQL compatibility DDL uses `NUMERIC`. SQLite's deployed legacy schema is imported and variable, so its actual column affinities and row values are **unknown** without a separately authorized disposable snapshot.
- `REAL` occurrences in the inspected server code are confined to synthetic SQLite tests. No query of production data was performed.
- No conversion, backfill, rounding, or destructive schema change is approved by this inventory. Financial history remains in place.
- Read-only synthetic linked-work reconciliation now compares legacy major-unit values with canonical integer-minor-unit facts using Decimal half-up rounding, reports matched/unlinked counts, and fails closed on drift. Tests cover exact PostgreSQL Decimal binding at the helper/repository boundary and retain SQLite float compatibility. A real imported snapshot rehearsal remains a separate gate; never use production as a test database. Fresh disposable PostgreSQL adapter-level coverage for the latest source change remains the next gate.
