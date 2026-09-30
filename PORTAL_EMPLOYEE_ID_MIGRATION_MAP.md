# PORTAL employee identity migration map

Read-only evidence. Canonical runtime identity target: employee_id.

## Priority summary

- P0 forbidden external runtime: 0
- P0 active runtime identity dependencies: 28
- P1 compatibility/import/schema boundaries: 37
- P2 history/test/fixture references: 119

P0 runtime identity dependencies are the actionable blockers for roadmap item 102. P1 bridges may remain temporarily when explicit, tested and isolated.

## Files requiring action

| File | P0 | P1 | P2 | Recommended action |
|---|---:|---:|---:|---|
| android_src/app/src/main/assets/app.js | 0 | 1 | 0 | Allowed temporarily: bridge is explicit and must remain covered by compatibility tests. |
| android_src/app/src/main/assets/core.js | 0 | 2 | 0 | Allowed temporarily: bridge is explicit and must remain covered by compatibility tests. |
| server/excel_apply.py | 0 | 3 | 0 | Keep as temporary migration bridge; exported/API identity should be employee_id and legacy mapping must be explicit. |
| server/excel_import.py | 0 | 2 | 0 | Keep as temporary migration bridge; exported/API identity should be employee_id and legacy mapping must be explicit. |
| server/excel_template.py | 0 | 2 | 0 | Keep as temporary migration bridge; exported/API identity should be employee_id and legacy mapping must be explicit. |
| server/migration_import.py | 0 | 1 | 0 | Keep as temporary migration bridge; exported/API identity should be employee_id and legacy mapping must be explicit. |
| server/portal_app_server.py | 24 | 13 | 0 | Review manually; move this shape behind the canonical employee_id adapter. |
| server/production_migrations.py | 0 | 2 | 0 | Retain historical schema/FK until additive migration and rollback rehearsal prove removal safe. |
| server/production_repository.py | 4 | 6 | 0 | Make employee_id the service/repository contract; translate to legacy ids only inside one compatibility boundary. |
| server/production_service.py | 0 | 5 | 0 | Allowed temporarily: bridge is explicit and must remain covered by compatibility tests. |

## P0 line evidence

| File | Line | Evidence |
|---|---:|---|
| server/portal_app_server.py | 243 | tg = user.get("telegram_id") |
| server/portal_app_server.py | 246 | rows = conn.execute("SELECT client_id FROM manager_client_assignments WHERE telegram_id=? AND active=1", (tg,)).fetchall() |
| server/portal_app_server.py | 299 | SELECT 1 FROM payroll_payments WHERE telegram_id=? AND period_start=? AND period_end=? AND status='paid' |
| server/portal_app_server.py | 356 | INSERT INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) |
| server/portal_app_server.py | 361 | INSERT OR IGNORE INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) |
| server/portal_app_server.py | 374 | worker_id = user.get("telegram_id") |
| server/portal_app_server.py | 437 | params.append(user.get("telegram_id")) |
| server/portal_app_server.py | 439 | worker_filter = " AND client IN (SELECT c.name FROM portal_clients c JOIN manager_client_assignments a ON a.client_id=c.id WHERE a.telegram_id=? AND a.active=1)" |
| server/portal_app_server.py | 440 | params.append(user.get("telegram_id")) |
| server/portal_app_server.py | 505 | row = conn.execute("SELECT MIN(telegram_id) FROM employees WHERE company_id=? AND telegram_id<0", (company_id,)).fetchone() |
| server/portal_app_server.py | 507 | row = conn.execute("SELECT MIN(telegram_id) FROM employees WHERE telegram_id<0").fetchone() |
| server/portal_app_server.py | 533 | values.update({k: body[k] for k in ("username", "display_name", "role", "telegram_id", "active") if k in body}) |
| server/portal_app_server.py | 568 | conn.execute("UPDATE app_users SET username=?,display_name=?,role=?,telegram_id=?,active=?,pin_salt=?,pin_hash=?,updated_at=? WHERE id=?", |
| server/portal_app_server.py | 573 | user_id = conn.execute("INSERT INTO app_users(username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", |
| server/portal_app_server.py | 1003 | cur=conn.execute("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,telegram_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", |
| server/portal_app_server.py | 1106 | if not user.get("telegram_id"): return self.send_json({"ok":True,"rows":[]}) |
| server/portal_app_server.py | 1108 | rows=[dict(r) for r in conn.execute("SELECT id,client,operation,quantity,rate,salary,created_at FROM work_log WHERE telegram_id=? ORDER BY id DESC LIMIT 50",(user["telegram_id"],)).fetchall()] |
| server/portal_app_server.py | 1112 | if not user.get("telegram_id"): return self.send_json({"ok":True,"data":{"quantity":0,"accrued":0,"paid":0,"remaining":0}}) |
| server/portal_app_server.py | 1115 | q=conn.execute("SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(salary),0) FROM work_log WHERE telegram_id=? AND created_at BETWEEN ? AND ?",(user["telegram_id"],s,e)).fetchone() |
| server/portal_app_server.py | 1116 | paid=conn.execute("SELECT COALESCE(SUM(amount),0) FROM payroll_transactions WHERE telegram_id=? AND period_start=? AND period_end=?",(user["telegram_id"],s,e)).fetchone()[0] if table_exists(conn,"payroll_transactions") else 0 |
| server/portal_app_server.py | 1141 | client_filter = "WHERE i.client IN (SELECT c.name FROM portal_clients c JOIN manager_client_assignments a ON a.client_id=c.id WHERE a.telegram_id=? AND a.active=1)" |
| server/portal_app_server.py | 1142 | params = (user.get("telegram_id"),) |
| server/portal_app_server.py | 1152 | rows=[with_employee_id(r) for r in conn.execute("SELECT id,username,display_name,role,telegram_id,active,created_at FROM app_users ORDER BY display_name").fetchall()] |
| server/portal_app_server.py | 1153 | employees=[with_employee_id(r) for r in conn.execute("SELECT telegram_id,full_name,username FROM employees ORDER BY full_name").fetchall()] |
| server/production_repository.py | 85 | SELECT e.company_id,e.telegram_id FROM employees e |
| server/production_repository.py | 88 | WHERE i.company_id=e.company_id AND i.legacy_employee_id=e.telegram_id) |
| server/production_repository.py | 107 | 'SELECT 1 FROM '+table+' WHERE company_id=? AND telegram_id=? ' |
| server/production_repository.py | 177 | paid=self.sql("SELECT 1 FROM payroll_payments WHERE company_id=? AND telegram_id=? AND period_start<=? AND period_end>=? AND status='paid'",(self.company_id,employee,created.replace('T',' ')[:19],created.replace('T',' ')[:19])).fetchone() |
