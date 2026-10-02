"""Isolation regressions against independent databases, including colliding IDs."""
import concurrent.futures
import json
import sqlite3
import threading
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import test_portal_app_server as legacy

portal = legacy.portal
tenants = portal.tenants


class CompanyIsolationTest(unittest.TestCase):
    request = legacy.PortalAPITest.request
    tearDown = legacy.PortalAPITest.tearDown

    def setUp(self):
        legacy.PortalAPITest.setUp(self)
        with portal.db() as conn:
            conn.executescript("""
            CREATE TABLE materials(id INTEGER PRIMARY KEY,name TEXT,unit TEXT,stock_qty REAL,min_stock REAL,unit_cost REAL,active INTEGER,updated_at TEXT);
            CREATE TABLE operation_material_norms(operation_id INTEGER,material_id INTEGER,qty_per_unit REAL,active INTEGER);
            CREATE TABLE material_movements(material_id INTEGER,qty_change REAL,unit_cost REAL,movement_type TEXT,reference_type TEXT,reference_id TEXT,note TEXT,created_at TEXT,created_by INTEGER);
            CREATE TABLE work_material_consumption(work_id INTEGER,material_id INTEGER,quantity REAL,unit_cost REAL,updated_at TEXT,PRIMARY KEY(work_id,material_id));
            CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,client TEXT,active INTEGER,material_cost_per_unit REAL,other_cost_per_unit REAL);
            CREATE TABLE tariff_versions(id INTEGER PRIMARY KEY,client TEXT,operation TEXT,valid_to TEXT);
            CREATE TABLE portal_client_requisites(client_id INTEGER,legal_name TEXT,inn TEXT,kpp TEXT,phone TEXT,email TEXT,contact_person TEXT);
            CREATE TABLE audit_log(actor_id INTEGER,action TEXT,entity_type TEXT,entity_id TEXT,details TEXT,created_at TEXT);
            """)
        portal.ensure_schema()
        self.owner_id = portal.create_platform_owner("owner", "Owner-secret-canary-123")
        self.owner = self.request("/api/platform/login", body={"username":"owner","pin":"Owner-secret-canary-123"})["token"]
        self.other = self.request("/api/platform/companies", self.owner, {"name":"Other company"})["id"]
        with tenants.company_scope(self.other):
            # Deliberately reuse every business ID, name and employee telegram_id.
            with portal.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM work_log").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0], 0)
                conn.execute("INSERT INTO employees(telegram_id,full_name,username) VALUES(101,'Other Worker','one')")
                conn.execute('INSERT INTO payroll_employee_identities(company_id,legacy_employee_id) VALUES(?,?)',(self.other,101))
            admin = portal.save_user({"username":"admin","pin":"5678","role":"admin"})
            worker = portal.save_user({"username":"worker","pin":"5678","role":"packer","telegram_id":101})
            self.other_client = portal.save_client({"name":"Client"})
            self.other_op = portal.save_operation({"name":"Packing","employee_rate":9,"client_rate":20},self.other_client)
            with portal.db() as conn:
                self.other_admin = portal.create_session(conn, admin)
                self.other_worker = portal.create_session(conn, worker)
                conn.execute("INSERT INTO work_log(telegram_id,client,operation,quantity,rate,salary,revenue,direct_cost,created_at) VALUES(101,'Client','Packing',700,9,6300,14000,0,?)", (portal.now_text(),))
                conn.execute("INSERT INTO portal_clients(id,name,active,created_at,updated_at) VALUES(900,'Foreign only',1,?,?)", (portal.now_text(),portal.now_text()))
        for cid in (1, self.other):
            with tenants.company_scope(cid), portal.db() as conn:
                conn.execute("INSERT INTO materials(id,name,unit,stock_qty,min_stock,unit_cost,active) VALUES(1,'Tape','m',1000,10,2,1)")
                conn.execute("INSERT INTO operation_material_norms(operation_id,material_id,qty_per_unit,active) VALUES(1,1,2,1)")
                conn.execute("INSERT INTO client_invoices(id,client,amount_due,created_at) VALUES(1,'Client',?,?)", (100 * cid,portal.now_text()))
                conn.execute("INSERT INTO client_payments(invoice_id,amount) VALUES(1,?)", (10 * cid,))

    def role_token(self, role, company_id=1):
        with tenants.company_scope(company_id):
            uid = portal.save_user({"username":role,"pin":"4321","role":role,"telegram_id":101})
            with portal.db() as conn:
                return portal.create_session(conn, uid)

    def test_reads_isolate_all_company_data_even_with_colliding_ids(self):
        a = self.request("/api/dashboard", self.admin)["data"]
        b = self.request("/api/dashboard", self.other_admin)["data"]
        self.assertEqual((a["quantity"], b["quantity"]), (103,700))
        self.assertEqual(self.request("/api/work/mine",self.other_worker)["rows"][0]["salary"],6300)
        self.assertEqual(self.request("/api/payroll/mine",self.worker)["data"]["accrued"],6)
        self.assertEqual(self.request("/api/clients/1",self.other_admin)["stats"]["quantity"],700)
        self.assertEqual(self.request("/api/clients/1/operations",self.other_admin)["operations"][0]["employee_rate"],9)
        self.assertEqual(self.request("/api/invoices",self.admin)["invoices"][0]["paid"],10)
        self.assertEqual(self.request("/api/invoices",self.other_admin)["invoices"][0]["paid"],20)
        self.assertEqual(self.request("/api/jobs",self.other_worker)["jobs"],[])
        other_employees=self.request("/api/users",self.other_admin)["employees"]
        portal_employees=self.request("/api/users",self.admin)["employees"]
        self.assertTrue(other_employees)
        self.assertTrue(portal_employees)
        self.assertIn("Other Worker",{e["full_name"] for e in other_employees})
        self.assertNotIn("Other Worker",{e["full_name"] for e in portal_employees})
        self.request("/api/clients/900",self.admin,status=403)
        with portal.db() as conn:
            # Unmodified BOT queries still see only PORTAL business rows.
            self.assertEqual(conn.execute("SELECT SUM(quantity) FROM work_log").fetchone()[0],103)

    def test_company_selectors_cannot_override_authenticated_scope(self):
        for token in (self.admin,self.worker,self.role_token("director"),self.role_token("manager")):
            self.request("/api/dashboard", token, status=403, extra_headers={"X-Portal-Company":str(self.other)})
            self.request(f"/api/dashboard?company_id={self.other}", token, status=403)
            self.request("/api/work", token, {"company_id":self.other,"client_id":1,"operation_id":1,"quantity":2},status=403)
        self.request("/api/users",self.admin,{"username":"bad","pin":"1234","company_id":self.other},status=403)
        forged = str(self.other) + "." + self.admin.split(".",1)[1]
        self.request("/api/me",forged,status=401)
        self.request("/api/me","../../evil.token",status=401)
        self.request("/api/setup",body={"company_id":self.other,"pin":"1234"},status=403)

    def test_writes_rates_renames_and_materials_never_cross_company(self):
        self.request("/api/admin/clients/1/operations/1",self.other_admin,{"employee_rate":11})
        self.request("/api/work",self.other_worker,{"client_id":1,"operation_id":1,"quantity":3})
        self.request("/api/admin/clients/1",self.other_admin,{"name":"Renamed other"})
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT SUM(salary) FROM work_log").fetchone()[0],206)
            self.assertEqual(conn.execute("SELECT name FROM portal_clients WHERE id=1").fetchone()[0],"Client")
            self.assertEqual(conn.execute("SELECT stock_qty FROM materials").fetchone()[0],1000)
            self.assertEqual(conn.execute("SELECT employee_rate FROM portal_client_operations WHERE id=1").fetchone()[0],2)
        with tenants.company_scope(self.other), portal.db() as conn:
            self.assertEqual(conn.execute("SELECT SUM(salary) FROM work_log").fetchone()[0],6333)
            self.assertEqual(conn.execute("SELECT stock_qty FROM materials").fetchone()[0],994)
            self.assertEqual(conn.execute("SELECT DISTINCT client FROM work_log").fetchall()[0][0],"Renamed other")
            self.assertEqual(conn.execute("SELECT company_id FROM material_movements").fetchone()[0],self.other)

    def test_manager_client_assignments_apply_to_dashboard_and_details(self):
        manager = self.role_token("manager")
        other_manager = self.role_token("manager", self.other)
        unassigned = portal.save_client({"name":"Unassigned"})
        with portal.db() as conn:
            conn.execute("INSERT INTO manager_client_assignments(telegram_id,client_id,active) VALUES(101,1,1)")
            conn.execute("INSERT INTO work_log(telegram_id,client,quantity,salary,revenue,direct_cost,created_at) VALUES(101,'Unassigned',999,999,999,0,?)", (portal.now_text(),))
            conn.execute("INSERT INTO client_invoices(id,client,amount_due,created_at) VALUES(2,'Unassigned',999,?)",(portal.now_text(),))
        self.assertEqual(self.request("/api/dashboard",manager)["data"]["quantity"],103)
        self.assertEqual(self.request("/api/dashboard",manager)["data"]["invoiced"],100)
        self.assertEqual(self.request("/api/dashboard",other_manager)["data"]["quantity"],0)
        self.assertEqual(len(self.request("/api/invoices",manager)["invoices"]),1)
        self.assertEqual(len(self.request("/api/clients",manager)["clients"]),1)
        self.request(f"/api/clients/{unassigned}",manager,status=403)
        self.request(f"/api/clients/{unassigned}/operations",manager,status=403)

    def test_manager_records_only_own_work_for_assigned_clients(self):
        manager = self.role_token("manager")
        other_manager = self.role_token("manager", self.other)
        body = {"client_id":1,"operation_id":1,"quantity":4}
        self.request("/api/work",manager,body,status=400)
        with portal.db() as conn:
            conn.execute("INSERT INTO manager_client_assignments(telegram_id,client_id,active) VALUES(101,1,1)")
        self.request("/api/work",manager,dict(body,employee_id=self.employee_202),status=400)
        saved = self.request("/api/work",manager,body)["work"]
        self.assertEqual(saved["salary"],8)
        with portal.db() as conn:
            row = conn.execute("SELECT telegram_id,company_id FROM work_log WHERE id=?",(saved["id"],)).fetchone()
            self.assertEqual(tuple(row),(101,1))
        self.request("/api/work",other_manager,body,status=400)
        self.request("/api/work",manager,dict(body,client_id=900),status=400)
        self.request("/api/work",manager,dict(body,company_id=self.other),status=403)
        self.request("/api/work",manager,body,status=403,extra_headers={"X-Portal-Company":str(self.other)})

    def test_platform_roles_and_audit_are_private_and_no_promotion_exists(self):
        for token in (self.admin,self.other_admin,self.worker,self.role_token("director"),self.role_token("manager"),self.role_token("accountant"),self.role_token("shift")):
            for path in ("/api/platform/companies","/api/platform/companies/1","/api/platform/audit"):
                self.request(path,token,status=403)
                self.request(path,token,{"monthly_price":1},status=403)
        self.request("/api/users",self.admin,{"username":"elevate","pin":"1234","role":"platform_owner"},status=400)
        self.request(f"/api/users/{self.worker_id}",self.admin,{"role":"platform_owner"},status=400)
        self.request("/api/company",self.admin,{"user_limit":99},status=405)
        director = self.request("/api/login",body={"username":"director","pin":"4321"})["token"]
        self.request("/api/users",director,status=403)
        self.request("/api/invoices",director)
        self.request("/api/materials",director)

    def test_god_uses_normal_login_and_never_appears_in_company_users(self):
        result=self.request("/api/login",body={"username":"owner","pin":"Owner-secret-canary-123","company_id":1})
        self.assertTrue(result['token'].startswith('p.'))
        self.assertEqual(result['user']['role'],'platform_owner')
        me=self.request('/api/me',result['token'])['user']
        self.assertEqual(me['role_label'],'God')
        company_users=self.request('/api/users',self.admin)['users']
        self.assertNotIn('owner',{row['username'] for row in company_users})
        with tenants.control(portal.DB_PATH) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM platform_owners WHERE username='owner'").fetchone()[0],1)
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users WHERE username='owner'").fetchone()[0],0)

    def test_company_audit_hides_god_actor(self):
        from production_repository import Repository
        from production_migrations import migrate
        with tenants.company_scope(1),portal.db() as conn:
            migrate(conn,1)
            repo=Repository(conn,1)
            repo.audit({'id':self.owner_id,'technical_owner':True},'god.hidden.test','x')
            conn.commit()
        tenant_view=self.request('/api/v3/audit?action=god.hidden.test',self.admin)['data']
        self.assertEqual(tenant_view['total'],0)
        god_view=self.request('/api/v3/audit?action=god.hidden.test',self.owner,extra_headers={'X-Portal-Company':'1'})['data']
        self.assertEqual(god_view['total'],1)

    def test_god_explicit_company_access_is_audited_without_secrets(self):
        self.request("/api/dashboard",self.owner,status=403)
        selected={"X-Portal-Company":str(self.other)}
        self.assertEqual(self.request("/api/dashboard",self.owner,extra_headers=selected)["data"]["quantity"],700)
        self.request("/api/users",self.owner,{"username":"audit_canary","pin":"PIN-canary-8976","role":"manager"},extra_headers=selected)
        self.request("/api/platform/login",body={"username":"owner","pin":"bad-password-canary"},status=401)
        self.request("/api/platform/companies/2",self.owner,{"monthly_price":123456,"user_limit":30})
        rows = self.request("/api/platform/audit",self.owner)["rows"]
        encoded=json.dumps(rows)
        for secret in ("Owner-secret-canary-123","PIN-canary-8976","bad-password-canary",self.owner,self.other_admin):
            self.assertNotIn(secret,encoded)
        self.assertTrue(any(r["event"]=="god_login" and r["outcome"]=="denied" for r in rows))
        self.assertTrue(any(r["event"]=="god_access" and r["company_id"]==self.other for r in rows))
        self.assertTrue(any(r["event"]=="company_updated" for r in rows))
        sample=next(r for r in rows if r["event"]=="god_access" and r["company_id"]==self.other)
        filtered=self.request('/api/platform/audit?company_id='+str(self.other)+'&actor_id='+str(sample['actor_id'])+
                              '&event=god_access&from='+sample['created_at'][:10]+'&to='+sample['created_at'][:10]+
                              '&page=1&limit=1',self.owner)
        self.assertGreaterEqual(filtered['total'],1)
        self.assertEqual((filtered['page'],filtered['limit'],len(filtered['rows'])),(1,1,1))
        self.assertEqual(filtered['rows'][0]['id'],sample['id'])
        if filtered['total']>1:
            next_page=self.request('/api/platform/audit?company_id='+str(self.other)+'&actor_id='+str(sample['actor_id'])+
                                   '&event=god_access&from='+sample['created_at'][:10]+'&to='+sample['created_at'][:10]+
                                   '&page=2&limit=1',self.owner)
            self.assertEqual((next_page['page'],len(next_page['rows'])),(2,1))
            self.assertNotEqual(next_page['rows'][0]['id'],sample['id'])
        self.request('/api/platform/audit?page=0',self.owner,status=400)
        with tenants.control(portal.DB_PATH) as conn:
            for sql in ("DELETE FROM platform_audit", "UPDATE platform_audit SET outcome='changed'", "INSERT OR REPLACE INTO platform_audit SELECT * FROM platform_audit LIMIT 1"):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)
        with portal.db() as conn:
            self.assertFalse(portal.table_exists(conn,"platform_audit"))

    def test_company_limits_activation_and_individual_override(self):
        self.assertIsNone(tenants.get_company(portal.DB_PATH,1)["user_limit"])
        self.assertEqual(tenants.get_company(portal.DB_PATH,self.other)["user_limit"],15)
        with tenants.company_scope(self.other), portal.db() as conn:
            # Fill capacity without paying the cost of hashing test-only PINs.
            conn.executemany("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,active,created_at,updated_at) VALUES(?,?,'','', 'manager',1,?,?)",
                             [(f"seat{i}",f"Seat {i}",portal.now_text(),portal.now_text()) for i in range(13)])
        body={"username":"extra","pin":"1234","role":"manager"}
        self.request("/api/users",self.other_admin,body,status=400)
        inactive = self.request("/api/users",self.other_admin,dict(body,active=0))["id"]
        self.request(f"/api/users/{inactive}",self.other_admin,{"active":1},status=400)
        self.request("/api/platform/companies/2",self.owner,{"user_limit":14},status=400)
        self.request("/api/platform/companies/2",self.owner,{"user_limit":16})
        self.request(f"/api/users/{inactive}",self.other_admin,{"active":1})
        self.request("/api/platform/companies/1",self.owner,{"user_limit":15},status=400)
        # PORTAL remains unlimited even beyond the external-company default.
        with portal.db() as conn:
            conn.executemany("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,active,created_at,updated_at) VALUES(?,?,'','','manager',1,?,?)",
                             [(f"main{i}",f"Main {i}",portal.now_text(),portal.now_text()) for i in range(16)])
        self.request("/api/users",self.admin,body)

    def test_platform_module_toggles_persist_and_enforce_on_server_routes(self):
        company_path=f"/api/platform/companies/{self.other}"
        original=self.request(company_path,self.owner)["company"]
        self.assertEqual(original["module_toggles"],{})
        self.request(company_path,self.owner,{"module_toggles":{"work":False,"radar":False}})
        current=self.request(company_path,self.owner)["company"]
        self.assertEqual(current["module_toggles"],{"radar":False,"work":False})
        work_body={"client_id":1,"operation_id":1,"quantity":1}
        self.request("/api/work",self.other_worker,work_body,status=403)
        self.request("/api/v3/finance",self.other_admin,status=403)
        self.request("/api/work",self.worker,work_body)
        self.request(company_path,self.owner,{"module_toggles":{"work":True,"radar":True}})
        self.request("/api/work",self.other_worker,work_body)
        for invalid in ({"not-a-module":False},{"work":0},{"payroll":None},[]):
            self.request(company_path,self.owner,{"module_toggles":invalid},status=400)
        self.request("/api/platform/companies/1",self.owner,{"module_toggles":{"work":False}})
        self.request("/api/work",self.worker,work_body,status=403)
        self.request("/api/platform/companies/1",self.owner,{"module_toggles":{}})

    def test_company_status_demo_and_price_validation(self):
        self.request("/api/platform/companies/2",self.owner,{"status":"suspended"})
        self.request("/api/me",self.other_admin,status=401)
        self.request("/api/login",body={"username":"admin","pin":"5678","company_id":2},status=403)
        self.request("/api/dashboard",self.owner,extra_headers={"X-Portal-Company":"2"})
        self.request("/api/platform/companies/2",self.owner,{"status":"active","service_status":"expired"})
        self.request("/api/me",self.other_admin,status=401)
        past=datetime.now()-timedelta(days=2)
        self.request("/api/platform/companies/2",self.owner,{"service_status":"active","demo_enabled":1,"demo_start":past.isoformat(),"demo_end":(past+timedelta(days=1)).isoformat()})
        self.request("/api/me",self.other_admin,status=401)
        for body in ({"monthly_price":-1},{"monthly_price":1.5},{"demo_end":"bad"},{"demo_start":"2100-01-01"},{"user_limit":None},{"path":"/tmp/other.db"}):
            self.request("/api/platform/companies/2",self.owner,body,status=400)
        self.request("/api/platform/companies/2",self.owner,{"demo_enabled":0})
        self.request("/api/me",self.other_admin)

    def test_concurrent_last_seat_cannot_exceed_company_limit(self):
        self.request("/api/platform/companies/2",self.owner,{"user_limit":3})
        barrier = threading.Barrier(2)
        def create(index):
            with tenants.company_scope(self.other):
                barrier.wait(timeout=5)
                try:
                    portal.save_user({"username":f"race{index}","pin":"1234","role":"manager"})
                    return "created"
                except ValueError:
                    return "limited"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(create,(1,2)))
        self.assertEqual(sorted(results),["created","limited"])
        with tenants.company_scope(self.other),portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users WHERE active=1").fetchone()[0],3)

    def test_god_rejected_target_is_audited_and_no_target_is_implicit(self):
        for target in ("99999","../secret-canary", "0"):
            self.request("/api/dashboard",self.owner,status=403,extra_headers={"X-Portal-Company":target})
        rows=self.request("/api/platform/audit",self.owner)["rows"]
        denied=[r for r in rows if r["event"]=="god_access" and r["outcome"]=="failed"]
        self.assertEqual(len(denied),3)
        self.assertTrue(all(json.loads(r["details"])["status"]==403 for r in denied))
        self.assertNotIn("secret-canary",json.dumps(rows))

    def test_company_id_database_constraints_and_atomic_context_reset(self):
        for cid in (1,self.other):
            with tenants.company_scope(cid), portal.db() as conn:
                for bad in (None,999):
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute("UPDATE work_log SET company_id=?",(bad,))
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                    self.assertIn("company_id",portal.columns(conn,tenants.quote(row[0])))
        with self.assertRaises(RuntimeError):
            with tenants.company_scope(self.other):
                raise RuntimeError("test")
        self.assertEqual(tenants.COMPANY_ID.get(),1)
        def read(cid):
            with tenants.company_scope(cid), portal.db() as conn:
                return conn.execute("SELECT SUM(quantity) FROM work_log").fetchone()[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(read,cid) for cid in (1,self.other)*5]
            self.assertEqual([f.result() for f in futures],[103,700]*5)

    def test_migration_idempotent_history_and_legacy_sessions_preserved(self):
        with portal.db() as conn:
            before=[tuple(r) for r in conn.execute("SELECT * FROM work_log ORDER BY id")]
            conn.execute("UPDATE app_sessions SET token='legacy-token-without-prefix' WHERE token=?",(self.admin,))
            conn.execute("INSERT INTO payroll_transactions(telegram_id,period_start,period_end,amount) VALUES(101,'old-start','old-end',456)")
        portal.ensure_schema()
        portal.ensure_schema()
        self.request("/api/me","legacy-token-without-prefix")
        with portal.db() as conn:
            self.assertEqual(before,[tuple(r) for r in conn.execute("SELECT * FROM work_log ORDER BY id")])
            self.assertEqual(conn.execute("SELECT amount FROM payroll_transactions").fetchone()[0],456)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        self.assertEqual(self.request("/api/dashboard",self.other_admin)["data"]["quantity"],700)


class MigrationTest(unittest.TestCase):
    def test_existing_b005_rows_and_auth_survive_first_migration_exactly(self):
        old_path = portal.DB_PATH
        with tempfile.TemporaryDirectory(prefix="portal-migration-") as directory:
            try:
                portal.DB_PATH = str(Path(directory)/"legacy.db")
                with tenants.connect_file(portal.DB_PATH, create=True) as conn:
                    conn.executescript(legacy.SCHEMA)
                    conn.executescript("""
                    CREATE TABLE app_users(id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,pin_salt TEXT NOT NULL,pin_hash TEXT NOT NULL,role TEXT NOT NULL,telegram_id INTEGER,active INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                    CREATE TABLE app_sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES app_users(id));
                    INSERT INTO app_users VALUES(7,'legacy','Legacy Admin','salt','hash','admin',101,1,'2020','2020');
                    INSERT INTO app_sessions VALUES('old-session',7,'2020','2099-12-31 23:59:59');
                    INSERT INTO portal_clients VALUES(8,'Old Client',1,'2020','2020');
                    INSERT INTO portal_client_operations VALUES(9,8,'Old Operation',2,5,1,0,'2020','2020');
                    INSERT INTO work_log VALUES(42,101,'one','Worker','Old Client','Old Operation',10,2,20,'2020',NULL,5,50,3);
                    INSERT INTO payroll_payments VALUES(101,'2020-01-01','2020-01-15','paid');
                    INSERT INTO payroll_transactions VALUES(101,'2020-01-01','2020-01-15',20);
                    INSERT INTO client_invoices VALUES(4,'Old Client','History',50,NULL,'2020',NULL);
                    INSERT INTO client_payments VALUES(4,30);
                    """)
                    snapshots={}
                    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                        fields=[r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
                        snapshots[table]=(fields,[tuple(r) for r in conn.execute(f'SELECT * FROM "{table}"')])
                portal.ensure_schema()
                portal.ensure_schema()
                with portal.db() as conn:
                    for table,(fields,rows) in snapshots.items():
                        actual=[tuple(r) for r in conn.execute(f'SELECT {",".join(fields)} FROM "{table}"')]
                        self.assertEqual(actual,rows,table)
                        self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE company_id IS NULL OR company_id!=1').fetchone()[0],0)
                    self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                user=portal.user_from_token("old-session")
                self.assertEqual((user["id"],user["role"],user["company_id"]),(7,"admin",1))
                with tenants.control(portal.DB_PATH) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM platform_owners").fetchone()[0],0)
            finally:
                portal.DB_PATH=old_path

    def test_conflicting_company_data_rolls_back_migration(self):
        old_path=portal.DB_PATH
        with tempfile.TemporaryDirectory(prefix="portal-migration-") as directory:
            try:
                portal.DB_PATH=str(Path(directory)/"bad.db")
                with tenants.connect_file(portal.DB_PATH, create=True) as conn:
                    conn.executescript(legacy.SCHEMA)
                    conn.execute("ALTER TABLE employees ADD COLUMN company_id INTEGER DEFAULT 2")
                    before=[tuple(r) for r in conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]
                with self.assertRaises(RuntimeError):
                    portal.ensure_schema()
                with tenants.connect_file(portal.DB_PATH) as conn:
                    self.assertEqual(before,[tuple(r) for r in conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")])
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],2)
            finally:
                portal.DB_PATH=old_path


if __name__ == "__main__":
    unittest.main()
