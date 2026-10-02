# PORTAL money field inventory

Generated inventory for roadmap item 105. No schema or values are changed.

## Summary

- legacy float-like money declarations: 61
- explicit minor-unit money declarations: 3
- source references to cents/minor-unit conversion: 39

## Migration policy

- New monetary storage/calculation should use integer minor units.
- Legacy REAL/NUMERIC money must not be dropped or silently rewritten.
- Migration must be additive, deterministic, reconciled and rehearsed on disposable PostgreSQL.
- Quantity/weight fields are intentionally excluded from money classification.

## Legacy float-like money declarations

| File | Line | Field | SQL type | Evidence |
|---|---:|---|---|---|
| server/migrations/postgresql_core_stage4b.sql | 51 | employee_rate | NUMERIC | name TEXT NOT NULL, employee_rate NUMERIC, client_rate NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 51 | client_rate | NUMERIC | name TEXT NOT NULL, employee_rate NUMERIC, client_rate NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 65 | rate | NUMERIC | quantity NUMERIC, rate NUMERIC, salary NUMERIC, client_rate NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 65 | salary | NUMERIC | quantity NUMERIC, rate NUMERIC, salary NUMERIC, client_rate NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 65 | client_rate | NUMERIC | quantity NUMERIC, rate NUMERIC, salary NUMERIC, client_rate NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 66 | revenue | NUMERIC | revenue NUMERIC, direct_cost NUMERIC, created_at TEXT, updated_at TEXT, |
| server/migrations/postgresql_core_stage4b.sql | 66 | direct_cost | NUMERIC | revenue NUMERIC, direct_cost NUMERIC, created_at TEXT, updated_at TEXT, |
| server/migrations/postgresql_core_stage4b.sql | 75 | amount | NUMERIC | period_end TEXT, amount NUMERIC |
| server/migrations/postgresql_core_stage4b.sql | 79 | amount_due | NUMERIC | amount_due NUMERIC, due_date TEXT, created_at TEXT, closed_at TEXT, |
| server/migrations/postgresql_core_stage4b.sql | 83 | amount | NUMERIC | company_id BIGINT NOT NULL, invoice_id BIGINT, amount NUMERIC, |
| server/migrations/postgresql_core_stage4b.sql | 88 | unit_cost | NUMERIC | unit TEXT, unit_cost NUMERIC, stock_qty NUMERIC, active INTEGER NOT NULL DEFAULT 1, |
| server/migrations/postgresql_core_stage4b.sql | 93 | unit_cost | NUMERIC | qty_change NUMERIC, unit_cost NUMERIC, movement_type TEXT, reference_type TEXT, |
| server/migrations/postgresql_core_stage4b.sql | 108 | internal_cost | NUMERIC | due_at TEXT, updated_at TEXT, completed_at TEXT, internal_cost NUMERIC, |
| server/migrations/postgresql_runtime.sql | 36 | unit_cost | NUMERIC | unit_cost NUMERIC NOT NULL, |
| server/migrations/postgresql_stage4c.sql | 21 | material_cost_per_unit | NUMERIC | material_cost_per_unit NUMERIC NOT NULL DEFAULT 0, |
| server/migrations/postgresql_stage4c.sql | 22 | other_cost_per_unit | NUMERIC | other_cost_per_unit NUMERIC NOT NULL DEFAULT 0, |
| server/migrations/postgresql_stage4c.sql | 35 | employee_rate | NUMERIC | employee_rate NUMERIC, |
| server/migrations/postgresql_stage4c.sql | 36 | client_rate | NUMERIC | client_rate NUMERIC, |
| server/migrations/postgresql_stage4c.sql | 54 | price | NUMERIC | price NUMERIC, |
| server/migrations/postgresql_stage4c.sql | 217 | unit_price | NUMERIC | unit_price NUMERIC NOT NULL, |
| server/migrations/postgresql_stage4c.sql | 218 | amount | NUMERIC | amount NUMERIC NOT NULL, |
| server/migrations/postgresql_stage4c.sql | 280 | amount | NUMERIC | amount NUMERIC NOT NULL, |
| server/migrations/postgresql_stage4c.sql | 358 | amount_paid | NUMERIC | amount_paid NUMERIC NOT NULL DEFAULT 0, |
| server/migrations/postgresql_stage4c.sql | 379 | amount_snapshot | NUMERIC | ALTER TABLE payroll_payments ADD COLUMN IF NOT EXISTS amount_snapshot NUMERIC; |
| server/migrations/postgresql_stage4c.sql | 398 | unit_direct_cost | NUMERIC | ALTER TABLE work_log ADD COLUMN IF NOT EXISTS unit_direct_cost NUMERIC NOT NULL DEFAULT 0; |
| server/migrations/postgresql_stage6_payroll_settlement.sql | 89 | balance | NUMERIC | DECLARE snapshot JSONB; legacy BIGINT; accrued NUMERIC; balance NUMERIC; |
| server/test_migration_import.py | 17 | employee_rate | REAL | CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL); |
| server/test_migration_import.py | 17 | client_rate | REAL | CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL); |
| server/test_migration_import.py | 18 | salary | REAL | CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL); |
| server/test_migration_import.py | 18 | revenue | REAL | CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL); |
| server/test_migration_import.py | 19 | amount_due | REAL | CREATE TABLE client_invoices(id INTEGER PRIMARY KEY,client TEXT,amount_due REAL); |
| server/test_migration_import.py | 20 | amount | REAL | CREATE TABLE client_payments(invoice_id INTEGER,amount REAL); |
| server/test_migration_import.py | 33 | employee_rate | REAL | CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL,company_id INTEGER); |
| server/test_migration_import.py | 33 | client_rate | REAL | CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL,company_id INTEGER); |
| server/test_migration_import.py | 34 | salary | REAL | CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL,company_id INTEGER); |
| server/test_migration_import.py | 34 | revenue | REAL | CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL,company_id INTEGER); |
| server/test_migration_import.py | 35 | amount_due | REAL | CREATE TABLE client_invoices(id INTEGER PRIMARY KEY,client TEXT,amount_due REAL,company_id INTEGER); |
| server/test_migration_import.py | 36 | amount | REAL | CREATE TABLE client_payments(invoice_id INTEGER,amount REAL,company_id INTEGER); |
| server/test_migration_validation.py | 25 | employee_rate | REAL | client_id INTEGER, employee_rate REAL, client_rate REAL); |
| server/test_migration_validation.py | 25 | client_rate | REAL | client_id INTEGER, employee_rate REAL, client_rate REAL); |
| server/test_migration_validation.py | 27 | salary | REAL | salary REAL, revenue REAL); |
| server/test_migration_validation.py | 27 | revenue | REAL | salary REAL, revenue REAL); |
| server/test_migration_validation.py | 28 | amount_due | REAL | CREATE TABLE client_invoices (id INTEGER, company_id INTEGER, amount_due REAL); |
| server/test_migration_validation.py | 29 | amount | REAL | CREATE TABLE client_payments (id INTEGER, company_id INTEGER, amount REAL); |
| server/test_migration_validation.py | 179 | salary | REAL | conn.execute('CREATE TABLE work_log (id INTEGER, salary REAL)') |
| server/test_portal_app_server.py | 30 | employee_rate | REAL | name TEXT NOT NULL, employee_rate REAL, client_rate REAL, active INTEGER DEFAULT 1, |
| server/test_portal_app_server.py | 30 | client_rate | REAL | name TEXT NOT NULL, employee_rate REAL, client_rate REAL, active INTEGER DEFAULT 1, |
| server/test_portal_app_server.py | 34 | rate | REAL | first_name TEXT, client TEXT, operation TEXT, quantity INTEGER, rate REAL, salary REAL, |
| server/test_portal_app_server.py | 34 | salary | REAL | first_name TEXT, client TEXT, operation TEXT, quantity INTEGER, rate REAL, salary REAL, |
| server/test_portal_app_server.py | 35 | client_rate | REAL | created_at TEXT, updated_at TEXT, client_rate REAL, revenue REAL, direct_cost REAL); |
| server/test_portal_app_server.py | 35 | revenue | REAL | created_at TEXT, updated_at TEXT, client_rate REAL, revenue REAL, direct_cost REAL); |
| server/test_portal_app_server.py | 35 | direct_cost | REAL | created_at TEXT, updated_at TEXT, client_rate REAL, revenue REAL, direct_cost REAL); |
| server/test_portal_app_server.py | 37 | amount | REAL | CREATE TABLE payroll_transactions (telegram_id INTEGER,period_start TEXT,period_end TEXT,amount REAL); |
| server/test_portal_app_server.py | 38 | amount_due | REAL | CREATE TABLE client_invoices (id INTEGER PRIMARY KEY,client TEXT,description TEXT,amount_due REAL, |
| server/test_portal_app_server.py | 40 | amount | REAL | CREATE TABLE client_payments (invoice_id INTEGER,amount REAL); |
| server/test_portal_app_server.py | 44 | internal_cost | REAL | internal_cost REAL); |
| server/test_portal_tenancy.py | 25 | unit_cost | REAL | CREATE TABLE materials(id INTEGER PRIMARY KEY,name TEXT,unit TEXT,stock_qty REAL,min_stock REAL,unit_cost REAL,active INTEGER,updated_at TEXT); |
| server/test_portal_tenancy.py | 27 | unit_cost | REAL | CREATE TABLE material_movements(material_id INTEGER,qty_change REAL,unit_cost REAL,movement_type TEXT,reference_type TEXT,reference_id TEXT,note TEXT,created_at TEXT,created_by INTEGER); |
| server/test_portal_tenancy.py | 28 | unit_cost | REAL | CREATE TABLE work_material_consumption(work_id INTEGER,material_id INTEGER,quantity REAL,unit_cost REAL,updated_at TEXT,PRIMARY KEY(work_id,material_id)); |
| server/test_portal_tenancy.py | 29 | material_cost_per_unit | REAL | CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,client TEXT,active INTEGER,material_cost_per_unit REAL,other_cost_per_unit REAL); |
| server/test_portal_tenancy.py | 29 | other_cost_per_unit | REAL | CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,client TEXT,active INTEGER,material_cost_per_unit REAL,other_cost_per_unit REAL); |
