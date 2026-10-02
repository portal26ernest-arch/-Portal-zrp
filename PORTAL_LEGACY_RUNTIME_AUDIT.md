# PORTAL legacy runtime identity audit

Generated evidence only; this tool does not modify schemas or data.

## Summary

- forbidden external Telegram/Termux runtime references: 0
- active runtime direct telegram_id references: 52
- active runtime compatibility bridges: 16
- schema/test/legacy references: 108

## Release interpretation

- External Telegram/Termux runtime count must remain zero.
- employee_id is the target canonical identity.
- Direct active-runtime telegram_id references mean roadmap item 102 is not yet fully complete.
- Historical columns may remain until an additive rehearsed migration proves safe.

## Active runtime findings

| Kind | File | Line | Evidence |
|---|---|---:|---|
| runtime_bridge | android_src/app/src/main/assets/app.js | 35 | const employeeId=user=>user?.employee_id??user?.telegram_id??null; |
| runtime_bridge | android_src/app/src/main/assets/core.js | 48 | if (page==='work') return !!(user.employee_id??user.telegram_id) && ['admin','director','manager','packer','shift'].includes(user.role); |
| runtime_bridge | android_src/app/src/main/assets/core.js | 49 | if (page==='payroll') return !!(user.employee_id??user.telegram_id); |
| runtime_direct_telegram_id | server/excel_apply.py | 67 | legacy=r.sql('SELECT MIN(telegram_id) FROM employees WHERE company_id=? AND telegram_id<0',(r.company_id,)).fetchone()[0] |
| runtime_direct_telegram_id | server/excel_apply.py | 69 | r.sql('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,?,?,?)', |
| runtime_direct_telegram_id | server/excel_apply.py | 74 | r.sql('UPDATE employees SET full_name=?,username=? WHERE company_id=? AND telegram_id=?', |
| runtime_direct_telegram_id | server/excel_import.py | 63 | result['_employees']=[dict(legacy_id=row[0],full_name=row[1],username=row[2] or '') for row in self.r.sql('SELECT telegram_id,full_name,username FROM employees WHERE company_id=? ORDER BY telegram_id',(self.r.company_id,)).fetchall()] |
| runtime_direct_telegram_id | server/excel_import.py | 144 | if not user or not mapping or user.get('telegram_id')!=mapping['legacy_employee_id']:raise ValueError('employee_user_identity_conflict') |
| runtime_direct_telegram_id | server/excel_template.py | 43 | FROM payroll_employee_identities i JOIN employees e ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id |
| runtime_direct_telegram_id | server/excel_template.py | 46 | accounts=[u for u in users if u.get('telegram_id')==legacy] |
| runtime_direct_telegram_id | server/migration_import.py | 21 | 'employees': {'telegram_id'}, |
| runtime_direct_telegram_id | server/portal_app_server.py | 132 | telegram_id INTEGER, |
| runtime_bridge | server/portal_app_server.py | 202 | if "employee_id" not in data:data["employee_id"]=data.get("telegram_id") |
| runtime_direct_telegram_id | server/portal_app_server.py | 243 | tg = user.get("telegram_id") |
| runtime_direct_telegram_id | server/portal_app_server.py | 246 | rows = conn.execute("SELECT client_id FROM manager_client_assignments WHERE telegram_id=? AND active=1", (tg,)).fetchall() |
| runtime_direct_telegram_id | server/portal_app_server.py | 299 | SELECT 1 FROM payroll_payments WHERE telegram_id=? AND period_start=? AND period_end=? AND status='paid' |
| runtime_direct_telegram_id | server/portal_app_server.py | 356 | INSERT INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) |
| runtime_direct_telegram_id | server/portal_app_server.py | 361 | INSERT OR IGNORE INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) |
| runtime_direct_telegram_id | server/portal_app_server.py | 374 | worker_id = user.get("telegram_id") |
| runtime_direct_telegram_id | server/portal_app_server.py | 410 | "telegram_id": worker_id, "username": user["username"], "first_name": first_name, |
| runtime_direct_telegram_id | server/portal_app_server.py | 436 | worker_filter=" AND telegram_id=?" |
| runtime_direct_telegram_id | server/portal_app_server.py | 437 | params.append(user.get("telegram_id")) |
| runtime_direct_telegram_id | server/portal_app_server.py | 439 | worker_filter = " AND client IN (SELECT c.name FROM portal_clients c JOIN manager_client_assignments a ON a.client_id=c.id WHERE a.telegram_id=? AND a.active=1)" |
| runtime_direct_telegram_id | server/portal_app_server.py | 440 | params.append(user.get("telegram_id")) |
| runtime_bridge | server/portal_app_server.py | 493 | found = conn.execute("SELECT 1 FROM employees WHERE company_id=? AND telegram_id=?", (tenants.COMPANY_ID.get(), employee_id)).fetchone() |
| runtime_bridge | server/portal_app_server.py | 495 | found = conn.execute("SELECT 1 FROM employees WHERE telegram_id=?", (employee_id,)).fetchone() |
| runtime_direct_telegram_id | server/portal_app_server.py | 505 | row = conn.execute("SELECT MIN(telegram_id) FROM employees WHERE company_id=? AND telegram_id<0", (company_id,)).fetchone() |
| runtime_direct_telegram_id | server/portal_app_server.py | 507 | row = conn.execute("SELECT MIN(telegram_id) FROM employees WHERE telegram_id<0").fetchone() |
| runtime_bridge | server/portal_app_server.py | 509 | values = {"telegram_id": employee_id, "full_name": display_name, "username": username, "company_id": company_id} |
| runtime_bridge | server/portal_app_server.py | 518 | if "telegram_id" in body and body["telegram_id"] != body["employee_id"]: |
| runtime_bridge | server/portal_app_server.py | 520 | body["telegram_id"]=body["employee_id"] |
| runtime_direct_telegram_id | server/portal_app_server.py | 532 | values = dict(old) if old else {"role": "packer", "telegram_id": None, "active": 1} |
| runtime_direct_telegram_id | server/portal_app_server.py | 533 | values.update({k: body[k] for k in ("username", "display_name", "role", "telegram_id", "active") if k in body}) |
| runtime_direct_telegram_id | server/portal_app_server.py | 545 | tg = validate_employee(conn, values["telegram_id"]) |
| runtime_direct_telegram_id | server/portal_app_server.py | 568 | conn.execute("UPDATE app_users SET username=?,display_name=?,role=?,telegram_id=?,active=?,pin_salt=?,pin_hash=?,updated_at=? WHERE id=?", |
| runtime_direct_telegram_id | server/portal_app_server.py | 573 | user_id = conn.execute("INSERT INTO app_users(username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", |
| runtime_direct_telegram_id | server/portal_app_server.py | 865 | self.request_user = dict(identity, role="admin", company_id=company_id, telegram_id=None, technical_owner=True) if is_owner else identity |
| runtime_direct_telegram_id | server/portal_app_server.py | 1003 | cur=conn.execute("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,telegram_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", |
| runtime_bridge | server/portal_app_server.py | 1006 | return self.send_json({"ok":True,"token":token,"user":{"username":username,"display_name":name,"role":"admin","employee_id":None,"telegram_id":None}}) |
| runtime_direct_telegram_id | server/portal_app_server.py | 1106 | if not user.get("telegram_id"): return self.send_json({"ok":True,"rows":[]}) |
| runtime_direct_telegram_id | server/portal_app_server.py | 1108 | rows=[dict(r) for r in conn.execute("SELECT id,client,operation,quantity,rate,salary,created_at FROM work_log WHERE telegram_id=? ORDER BY id DESC LIMIT 50",(user["telegram_id"],)).fetchall()] |
| runtime_direct_telegram_id | server/portal_app_server.py | 1112 | if not user.get("telegram_id"): return self.send_json({"ok":True,"data":{"quantity":0,"accrued":0,"paid":0,"remaining":0}}) |
| runtime_direct_telegram_id | server/portal_app_server.py | 1115 | q=conn.execute("SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(salary),0) FROM work_log WHERE telegram_id=? AND created_at BETWEEN ? AND ?",(user["telegram_id"],s,e)).fetchone() |
| runtime_direct_telegram_id | server/portal_app_server.py | 1116 | paid=conn.execute("SELECT COALESCE(SUM(amount),0) FROM payroll_transactions WHERE telegram_id=? AND period_start=? AND period_end=?",(user["telegram_id"],s,e)).fetchone()[0] if table_exists(conn,"payroll_transactions") else 0 |
| runtime_direct_telegram_id | server/portal_app_server.py | 1141 | client_filter = "WHERE i.client IN (SELECT c.name FROM portal_clients c JOIN manager_client_assignments a ON a.client_id=c.id WHERE a.telegram_id=? AND a.active=1)" |
| runtime_direct_telegram_id | server/portal_app_server.py | 1142 | params = (user.get("telegram_id"),) |
| runtime_direct_telegram_id | server/portal_app_server.py | 1152 | rows=[with_employee_id(r) for r in conn.execute("SELECT id,username,display_name,role,telegram_id,active,created_at FROM app_users ORDER BY display_name").fetchall()] |
| runtime_direct_telegram_id | server/portal_app_server.py | 1153 | employees=[with_employee_id(r) for r in conn.execute("SELECT telegram_id,full_name,username FROM employees ORDER BY full_name").fetchall()] |
| runtime_direct_telegram_id | server/production_migrations.py | 71 | r.sql('CREATE UNIQUE INDEX IF NOT EXISTS payroll_employee_legacy_scope ON employees(company_id,telegram_id)') |
| runtime_direct_telegram_id | server/production_migrations.py | 78 | FOREIGN KEY(company_id,legacy_employee_id) REFERENCES employees(company_id,telegram_id) |
| runtime_direct_telegram_id | server/production_repository.py | 85 | SELECT e.company_id,e.telegram_id FROM employees e |
| runtime_direct_telegram_id | server/production_repository.py | 88 | WHERE i.company_id=e.company_id AND i.legacy_employee_id=e.telegram_id) |
| runtime_direct_telegram_id | server/production_repository.py | 89 | ORDER BY e.telegram_id''', (self.company_id,)) |
| runtime_direct_telegram_id | server/production_repository.py | 96 | ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id |
| runtime_direct_telegram_id | server/production_repository.py | 107 | 'SELECT 1 FROM '+table+' WHERE company_id=? AND telegram_id=? ' |
| runtime_direct_telegram_id | server/production_repository.py | 151 | fields={'users':'id,display_name,role,telegram_id,active,company_id'}.get(name,'*') |
| runtime_bridge | server/production_repository.py | 156 | for row in rows:row['employee_id']=row.get('telegram_id') |
| runtime_bridge | server/production_repository.py | 174 | employee=user.get('employee_id',user.get('telegram_id')) |
| runtime_direct_telegram_id | server/production_repository.py | 177 | paid=self.sql("SELECT 1 FROM payroll_payments WHERE company_id=? AND telegram_id=? AND period_start<=? AND period_end>=? AND status='paid'",(self.company_id,employee,created.replace('T',' ')[:19],created.replace('T',' ')[:19])).fetchone() |
| runtime_direct_telegram_id | server/production_repository.py | 179 | values=dict(company_id=self.company_id,telegram_id=employee,username=user.get('username',''),first_name=user.get('display_name',''),client=client['name'],operation=operation['name'],quantity=quantity,rate=employee_rate/100,salary=quantity*employee_rate/100,cli |
| runtime_bridge | server/production_service.py | 50 | return user.get('employee_id',user.get('telegram_id')) |
| runtime_bridge | server/production_service.py | 71 | return any(a['client_id']==client_id and a['active'] and a['telegram_id']==employee_id(self.u) for a in self.r.catalog('assignments')) |
| runtime_direct_telegram_id | server/production_service.py | 329 | legacy=b.get('telegram_id') |
| runtime_bridge | server/production_service.py | 431 | values={key:params[key][0] for key in ('employee_id','telegram_id') if key in params} |
| runtime_bridge | server/production_service.py | 855 | if set(body)-{'company_id','employee_id','telegram_id','payroll_period_id','entry_type', |
| runtime_direct_telegram_id | server/web_pg_part10_fixture_host.py | 41 | "SELECT telegram_id FROM app_users WHERE id=?", (manager_id,)).fetchone() |
| runtime_direct_telegram_id | server/web_pg_part10_fixture_host.py | 44 | "(telegram_id,client_id,active,company_id) VALUES(?,1,1,1)", |
| runtime_direct_telegram_id | server/web_pg_part10_fixture_host.py | 45 | (manager["telegram_id"],)) |
