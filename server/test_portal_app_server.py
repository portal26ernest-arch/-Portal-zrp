"""API regression tests using an isolated fixture, never the phone's portal.db.

Run: python -m unittest discover -s server -p 'test_*.py' -v
Set PORTAL_TEST_HTTP=1 to exercise real loopback sockets as well.
The fixture models the columns used by b001; it is not a production DB migration.
"""
import gc
import http.client
import io
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import closing

spec = importlib.util.spec_from_file_location("portal", Path(__file__).with_name("portal_app_server.py"))
portal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portal)

SCHEMA = """
CREATE TABLE employees (telegram_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT);
INSERT INTO employees VALUES (101,'Worker One','one'),(202,'Worker Two','two');
CREATE TABLE portal_clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE portal_client_operations (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL,
 name TEXT NOT NULL, employee_rate REAL, client_rate REAL, active INTEGER DEFAULT 1,
 sort_order INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(client_id,name), FOREIGN KEY(client_id) REFERENCES portal_clients(id));
CREATE TABLE work_log (id INTEGER PRIMARY KEY, telegram_id INTEGER, username TEXT,
 first_name TEXT, client TEXT, operation TEXT, quantity INTEGER, rate REAL, salary REAL,
 created_at TEXT, updated_at TEXT, client_rate REAL, revenue REAL, direct_cost REAL);
CREATE TABLE payroll_payments (telegram_id INTEGER,period_start TEXT,period_end TEXT,status TEXT);
CREATE TABLE payroll_transactions (telegram_id INTEGER,period_start TEXT,period_end TEXT,amount REAL);
CREATE TABLE client_invoices (id INTEGER PRIMARY KEY,client TEXT,description TEXT,amount_due REAL,
 due_date TEXT,created_at TEXT,closed_at TEXT);
CREATE TABLE client_payments (invoice_id INTEGER,amount REAL);
CREATE TABLE manager_client_assignments (telegram_id INTEGER,client_id INTEGER,active INTEGER);
CREATE TABLE production_jobs (id INTEGER PRIMARY KEY,client TEXT,operation TEXT,product_name TEXT,
 status TEXT,target_quantity REAL,priority INTEGER,due_at TEXT,updated_at TEXT,completed_at TEXT,
 internal_cost REAL);
CREATE TABLE production_job_progress (job_id INTEGER,work_id INTEGER,telegram_id INTEGER,
 quantity REAL,created_at TEXT,UNIQUE(job_id,work_id));
"""


class QuietHandler(portal.Handler):
    def log_message(self, *args):
        pass


class MemorySocket:
    """Feed actual HTTP bytes through BaseHTTPRequestHandler without OS networking."""
    def __init__(self, data):
        self.data = data
        self.output = bytearray()

    def makefile(self, *args):
        return io.BytesIO(self.data)

    def sendall(self, data):
        self.output.extend(data)


class PortalAPITest(unittest.TestCase):
    def setUp(self):
        limiter_patch=patch.object(portal,'LOGIN_LIMITER',portal.LoginLimiter())
        limiter_patch.start();self.addCleanup(limiter_patch.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="portal-test-")
        self.old_db = portal.DB_PATH
        portal.DB_PATH = str(Path(self.tmp.name) / "fixture.db")
        conn = sqlite3.connect(portal.DB_PATH)
        conn.executescript(SCHEMA)
        conn.close()
        portal.ensure_schema()
        # Current API fixtures install the additive canonical identity map.
        # Separate migration tests below retain an unmigrated legacy database.
        with portal.db() as conn:
            conn.execute('''CREATE TABLE payroll_employee_identities (
                employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                legacy_employee_id INTEGER NOT NULL,
                UNIQUE(company_id,employee_id),
                UNIQUE(company_id,legacy_employee_id))''')
            conn.execute('''INSERT INTO payroll_employee_identities(company_id,legacy_employee_id)
                SELECT company_id,telegram_id FROM employees ORDER BY telegram_id''')
            self.employee_101=conn.execute('SELECT employee_id FROM payroll_employee_identities WHERE legacy_employee_id=101').fetchone()[0]
            self.employee_202=conn.execute('SELECT employee_id FROM payroll_employee_identities WHERE legacy_employee_id=202').fetchone()[0]
        self.admin_id = portal.save_user({"username":"admin","pin":"1234","role":"admin"})
        self.worker_id = portal.save_user({"username":"worker","pin":"1234","role":"packer","telegram_id":101})
        self.cid = portal.save_client({"name":"Client"})
        self.oid = portal.save_operation({"name":"Packing","employee_rate":2,"client_rate":5},self.cid)
        with portal.db() as conn:
            self.admin = portal.create_session(conn,self.admin_id)
            self.worker = portal.create_session(conn,self.worker_id)
            conn.executemany("INSERT INTO work_log(telegram_id,client,operation,quantity,rate,salary,revenue,direct_cost,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                             [(101,"Client","Packing",3,2,6,15,1,portal.now_text()),
                              (202,"Client","Packing",100,2,200,500,20,portal.now_text())])
            conn.execute("INSERT INTO production_jobs(id,client,operation,status,target_quantity,priority,internal_cost) VALUES(1,'Client','Packing','open',1000,1,999)")
        self.http = None
        if os.environ.get("PORTAL_TEST_HTTP") == "1":
            self.http = portal.ThreadingHTTPServer(("127.0.0.1",0),QuietHandler)
            self.thread = threading.Thread(target=self.http.serve_forever,daemon=True)
            self.thread.start()

    def tearDown(self):
        if self.http:
            self.http.shutdown()
            self.http.server_close()
            self.thread.join(timeout=3)
        portal.DB_PATH = self.old_db
        gc.collect()
        self.tmp.cleanup()

    def test_readiness_checks_both_planes_without_disclosing_errors(self):
        self.assertEqual(self.request('/api/ready'), {'ok': True, 'ready': True})
        with patch.object(portal.tenants, 'control', side_effect=ConnectionError('secret-dsn')):
            response = self.request('/api/ready', status=503)
        self.assertNotIn('secret-dsn', json.dumps(response))

    def request(self,path,token=None,body=None,method=None,status=200,extra_headers=None):
        headers = {"Authorization":"Bearer "+token} if token else {}
        headers.update(extra_headers or {})
        payload = json.dumps(body).encode() if body is not None else b""
        method = method or ("POST" if body is not None else "GET")
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.http:
            with closing(http.client.HTTPConnection("127.0.0.1",self.http.server_port,timeout=5)) as conn:
                conn.request(method,path,payload if body is not None else None,headers)
                response = conn.getresponse()
                data = json.loads(response.read())
                actual_status = response.status
        else:
            headers["Content-Length"] = str(len(payload))
            raw = f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n" + "".join(f"{k}: {v}\r\n" for k,v in headers.items()) + "\r\n"
            sock = MemorySocket(raw.encode()+payload)
            QuietHandler(sock,("127.0.0.1",12345),None)
            head,content=bytes(sock.output).split(b"\r\n\r\n",1)
            actual_status=int(head.split()[1])
            data=json.loads(content)
        self.assertEqual(actual_status,status,(path,data))
        return data

    def login(self,username="worker",pin="1234",status=200):
        return self.request("/api/login",body={"username":username,"pin":pin},status=status)

    def test_login_is_case_insensitive_and_usernames_are_case_unique(self):
        logged=self.login("WORKER","1234")
        self.assertEqual(logged["user"]["username"],"worker")
        self.request("/api/users",self.admin,{"username":"WoRkEr","display_name":"Duplicate","pin":"4321","role":"packer"},status=400)

    def test_self_service_pin_change_verifies_identity_revokes_other_sessions_and_preserves_current(self):
        with portal.db() as conn:
            other_session=portal.create_session(conn,self.worker_id)
        with patch.object(portal.Repository,"ready",return_value=True), patch.object(portal.Repository,"audit") as audit:
            self.assertEqual(self.request("/api/me/pin",self.worker,{"current_pin":"1234","new_pin":"5678"}),{"ok":True})
        audit.assert_called_once()
        audit_args,audit_kwargs=audit.call_args
        self.assertEqual(audit_args[1:],("user.pin.changed",self.worker_id))
        self.assertEqual(audit_kwargs,{})
        self.assertIsNotNone(portal.user_from_token(self.worker))
        self.assertIsNone(portal.user_from_token(other_session))
        self.login("worker","1234",status=401)
        self.assertEqual(self.login("worker","5678")["user"]["id"],self.worker_id)

    def test_self_service_pin_change_rejects_wrong_same_invalid_and_targeted_payloads_without_mutation(self):
        for payload in (
            {"current_pin":"wrong","new_pin":"5678"},
            {"current_pin":"1234","new_pin":"1234"},
            {"current_pin":"1234","new_pin":"123"},
            {"current_pin":"1234","new_pin":"x"*129},
            {"current_pin":"1234","new_pin":"5678","user_id":self.admin_id},
        ):
            self.request("/api/me/pin",self.worker,payload,status=400)
        self.login("worker","1234")
        self.request("/api/me/pin",status=401,body={"current_pin":"1234","new_pin":"5678"})

    def test_desktop_update_manifest_is_public_and_fail_closed(self):
        keys = {
            "PORTAL_DESKTOP_UPDATE_VERSION": "",
            "PORTAL_DESKTOP_UPDATE_BUILD": "",
            "PORTAL_DESKTOP_UPDATE_URL": "",
            "PORTAL_DESKTOP_UPDATE_SHA256": "",
            "PORTAL_DESKTOP_UPDATE_SIGNATURE": "",
        }
        with patch.dict(os.environ, keys, clear=False):
            self.request("/api/desktop-update", status=404)
        configured = {
            "PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0",
            "PORTAL_DESKTOP_UPDATE_BUILD": "37",
            "PORTAL_DESKTOP_UPDATE_URL": "https://downloads.example.test/PORTAL-Desktop-win-x64-3.7.0.zip",
            "PORTAL_DESKTOP_UPDATE_SHA256": "a" * 64,
            "PORTAL_DESKTOP_UPDATE_SIGNATURE": "B" * 512,
        }
        with patch.dict(os.environ, configured, clear=False):
            data = self.request("/api/desktop-update")
            self.assertEqual(data["build"], 37)
            self.assertNotIn("token", data)
            self.request("/api/desktop-update", body={}, status=405)

    def test_anonymous_denied_all_data_and_writes(self):
        for path in ("/api/me","/api/dashboard","/api/clients",f"/api/clients/{self.cid}",
                     f"/api/clients/{self.cid}/operations","/api/work/mine","/api/payroll/mine",
                     "/api/invoices","/api/materials","/api/jobs","/api/users","/api/admin/clients"):
            self.request(path,status=401)
        for path in ("/api/users",f"/api/users/{self.worker_id}","/api/admin/clients",
                     f"/api/admin/clients/{self.cid}",f"/api/admin/clients/{self.cid}/operations","/api/work"):
            self.request(path,body={},status=401)
        self.assertNotIn("db",self.request("/api/ping"))
        self.request("/api/setup",body={"username":"attacker","pin":"1234"},status=403)

    def test_setup_rejects_remote_identity_from_local_reverse_proxy_but_allows_local_operator(self):
        with portal.db() as conn:
            conn.execute("DELETE FROM app_sessions")
            conn.execute("DELETE FROM app_users")
        self.request("/api/setup", body={"username":"attacker","pin":"1234"}, status=403,
                     extra_headers={"X-Real-IP":"198.51.100.7"})
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0], 0)
        response=self.request("/api/setup", body={"username":"bootstrap","pin":"1234"})
        self.assertIn("token",response)
        self.request("/api/setup", body={"username":"replay","pin":"1234"}, status=403)

    def test_packer_cannot_read_finance_or_admin(self):
        for path in (f"/api/clients/{self.cid}","/api/invoices","/api/materials","/api/users","/api/admin/clients"):
            self.request(path,self.worker,status=403)
        for path in ("/api/users",f"/api/users/{self.worker_id}","/api/admin/clients",
                     f"/api/admin/clients/{self.cid}",f"/api/admin/clients/{self.cid}/operations",
                     f"/api/admin/clients/{self.cid}/operations/{self.oid}"):
            self.request(path,self.worker,{},status=403)
        operations = self.request(f"/api/clients/{self.cid}/operations",self.worker)["operations"]
        self.assertNotIn("client_rate",operations[0])
        self.assertNotIn("internal_cost",self.request("/api/jobs",self.worker)["jobs"][0])

    def test_other_roles_cannot_administer(self):
        for role in ("manager","accountant","shift","loader","driver"):
            uid=portal.save_user({"username":role,"pin":"1234","role":role})
            with portal.db() as conn:
                token=portal.create_session(conn,uid)
            self.request("/api/users",token,status=403)
            self.request("/api/admin/clients",token,{},status=403)
            self.request(f"/api/users/{self.worker_id}",token,{"role":"admin"},status=403)

    def test_personal_work_and_payroll_are_isolated(self):
        d=self.request("/api/dashboard",self.worker)["data"]
        self.assertEqual(d,{"period":"current","quantity":3.0,"salary":6.0})
        self.assertEqual(len(self.request("/api/work/mine",self.worker)["rows"]),1)
        self.assertEqual(self.request("/api/payroll/mine",self.worker)["data"]["accrued"],6)
        with portal.db() as conn:
            conn.execute("UPDATE app_users SET telegram_id=NULL WHERE id=?",(self.worker_id,))
        self.assertEqual(self.request("/api/dashboard",self.worker)["data"]["quantity"],0)
        self.assertEqual(self.request("/api/work/mine",self.worker)["rows"],[])
        self.assertEqual(self.request("/api/payroll/mine",self.worker)["data"]["accrued"],0)

    def test_new_user_gets_own_employee_without_existing_link(self):
        automatic=self.request("/api/users",self.admin,{"username":"fresh0","display_name":"Fresh Automatic","pin":"4321","role":"packer"})["id"]
        with portal.db() as conn:
            auto_employee=conn.execute("SELECT telegram_id FROM app_users WHERE id=?",(automatic,)).fetchone()[0]
            self.assertLess(auto_employee,0)
            self.assertEqual(conn.execute("SELECT full_name FROM employees WHERE telegram_id=?",(auto_employee,)).fetchone()[0],"Fresh Automatic")
        first=self.request("/api/users",self.admin,{"username":"fresh1","display_name":"Fresh One","pin":"4321","role":"packer","create_employee":True})["id"]
        second=self.request("/api/users",self.admin,{"username":"fresh2","display_name":"Fresh Two","pin":"4321","role":"director","create_employee":True})["id"]
        with portal.db() as conn:
            a=conn.execute("SELECT telegram_id FROM app_users WHERE id=?",(first,)).fetchone()[0]
            b=conn.execute("SELECT telegram_id FROM app_users WHERE id=?",(second,)).fetchone()[0]
            self.assertLess(a,0)
            self.assertLess(b,0)
            self.assertNotEqual(a,b)
            self.assertEqual(conn.execute("SELECT full_name FROM employees WHERE telegram_id=?",(a,)).fetchone()[0],"Fresh One")
            self.assertEqual(conn.execute("SELECT full_name FROM employees WHERE telegram_id=?",(b,)).fetchone()[0],"Fresh Two")
        with portal.db() as conn:
            before_link=conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        linked=self.request("/api/users",self.admin,{"username":"linked","display_name":"Existing","pin":"4321","role":"packer","employee_id":self.employee_202})["id"]
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT telegram_id FROM app_users WHERE id=?",(linked,)).fetchone()[0],202)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],before_link)

    def test_user_lifecycle_revokes_old_sessions(self):
        uid=self.request("/api/users",self.admin,{"username":"new","pin":"4321","role":"packer","employee_id":self.employee_202})["id"]
        token=self.login("new","4321")["token"]
        self.request(f"/api/users/{uid}",self.admin,{"role":"shift","pin":"9876","employee_id":self.employee_101})
        self.request("/api/me",token,status=401)
        self.login("new","4321",401)
        new=self.login("new","9876")
        self.assertEqual(new["user"]["role"],"shift")
        self.assertEqual(new["user"]["employee_id"],self.employee_101)
        self.request(f"/api/users/{uid}",self.admin,{"active":0})
        self.request("/api/me",new["token"],status=401)
        self.login("new","9876",401)
        self.request(f"/api/users/{uid}",self.admin,{"active":1})
        self.request("/api/me",new["token"],status=401)
        self.login("new","9876")
        users=self.request("/api/users",self.admin)["users"]
        self.assertTrue(all("pin_hash" not in u and "pin_salt" not in u for u in users))

    def test_last_admin_and_invalid_users(self):
        for body in ({"active":0},{"role":"shift"}):
            self.request(f"/api/users/{self.admin_id}",self.admin,body,status=400)
        for body in ({"telegram_id":999},{"telegram_id":None},{"role":"unknown"},{"pin":"1"},{"username":"admin"}):
            self.request(f"/api/users/{self.worker_id}",self.admin,body,status=400)
        self.assertEqual(self.request("/api/me",self.worker)["user"]["role"],"packer")

    def test_client_archive_restore_and_rename_preserve_history(self):
        cid=self.request("/api/admin/clients",self.admin,{"name":"New client"})["id"]
        self.request(f"/api/admin/clients/{cid}",self.admin,{"name":"Renamed","active":0})
        self.assertNotIn(cid,[c["id"] for c in self.request("/api/clients",self.worker)["clients"]])
        self.assertIn(cid,[c["id"] for c in self.request("/api/admin/clients",self.admin)["clients"]])
        self.request(f"/api/admin/clients/{cid}",self.admin,{"active":1})
        self.request(f"/api/admin/clients/{self.cid}",self.admin,{"name":"Client renamed"})
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*),SUM(salary),SUM(revenue) FROM work_log WHERE client='Client renamed'").fetchone()[:],(2,206,515))
            self.assertEqual(conn.execute("SELECT client FROM production_jobs").fetchone()[0],"Client renamed")
        self.request(f"/api/admin/clients/{self.cid}",self.admin,{"active":0})
        self.request("/api/work",self.worker,{"client_id":self.cid,"operation_id":self.oid,"quantity":2},status=400)
        self.request(f"/api/clients/{self.cid}/operations",self.worker,status=403)

    def test_operations_new_rates_apply_only_to_new_work(self):
        path=f"/api/admin/clients/{self.cid}/operations"
        new=self.request(path,self.admin,{"name":"Labelling","employee_rate":1.5,"client_rate":7})["id"]
        self.request(path+f"/{new}",self.admin,{"active":0})
        self.assertNotIn(new,[o["id"] for o in self.request(f"/api/clients/{self.cid}/operations",self.worker)["operations"]])
        self.request("/api/work",self.worker,{"client_id":self.cid,"operation_id":new,"quantity":2},status=400)
        self.request(path+f"/{new}",self.admin,{"active":1})
        self.request(path+f"/{self.oid}",self.admin,{"name":"Packing renamed","employee_rate":4,"client_rate":10})
        self.request("/api/work",self.worker,{"client_id":self.cid,"operation_id":self.oid,"quantity":2,"employee_id":self.employee_202},status=400)
        self.request("/api/work",self.worker,{"client_id":self.cid,"operation_id":self.oid,"quantity":2})
        with portal.db() as conn:
            rows=conn.execute("SELECT telegram_id,operation,quantity,salary,revenue FROM work_log ORDER BY id").fetchall()
            self.assertEqual(rows[0][:],(101,"Packing renamed",3,6,15))
            self.assertEqual(rows[-1][:],(101,"Packing renamed",2,8,20))
            self.assertEqual(conn.execute("SELECT SUM(quantity) FROM production_job_progress").fetchone()[0],2)

    def test_invalid_catalogue_changes_do_not_mutate(self):
        for body in ({"name":""},{"active":"false"},{"name":"Client"}):
            self.request("/api/admin/clients",self.admin,body,status=400)
        path=f"/api/admin/clients/{self.cid}/operations/{self.oid}"
        for rate in (-1,"NaN","Infinity",None,True):
            self.request(path,self.admin,{"employee_rate":rate},status=400)
        other=portal.save_client({"name":"Other"})
        self.request(f"/api/admin/clients/{other}/operations/{self.oid}",self.admin,{"name":"Wrong"},status=400)
        self.request("/api/admin/clients",self.admin,[],status=400)
        self.request("/api/clients",self.admin,{},status=405)
        for path,body in (("/api/admin/clients/0",{"name":"Must not create"}),
                          ("/api/users/0",{"username":"bad","pin":"1234","role":"admin"}),
                          (f"/api/admin/clients/{self.cid}/operations/0",{"name":"Bad","employee_rate":1,"client_rate":2})):
            self.request(path,self.admin,body,status=400)
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT employee_rate FROM portal_client_operations WHERE id=?",(self.oid,)).fetchone()[0],2)

    def test_schema_preserved_and_missing_database_not_created(self):
        portal.ensure_schema()
        with portal.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM work_log").fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0],2)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        missing=Path(self.tmp.name)/"must-not-be-created.db"
        portal.DB_PATH=str(missing)
        with self.assertRaises(sqlite3.OperationalError):
            portal.db()
        self.assertFalse(missing.exists())

    def test_audit_route_allowlist_labels_invitation_api_without_raw_paths(self):
        self.assertEqual(portal.audit_route('/api/v3/invitations'),'/api/v3/invitations')
        self.assertEqual(portal.audit_route('/api/v3/invitations/123'),'/api/v3/invitations/{id}')
        self.assertEqual(portal.audit_route('/api/v3/unlisted-secret-path'),'unknown')


class PostgreSQLDatabaseNameValidationTest(unittest.TestCase):
    def test_split_control_and_tenant_databases_are_supported(self):
        with patch.object(portal, 'CONFIG', SimpleNamespace(environment='test')):
            portal.validate_postgresql_database_names(
                'portal_test_control_runtime', 'portal_test_company_runtime')
            with self.assertRaises(RuntimeError):
                portal.validate_postgresql_database_names(
                    'portal_control_runtime', 'portal_test_company_runtime')
            with self.assertRaises(RuntimeError):
                portal.validate_postgresql_database_names(
                    'portal_test_control_runtime', 'portal_company_runtime')
        with patch.object(portal, 'CONFIG', SimpleNamespace(environment='production')):
            portal.validate_postgresql_database_names(
                'portal_prod_control', 'portal_prod_company_1')
            for control, tenant in (
                    ('portal_prod_control', 'portal_prod_control'),
                    ('portal_test_control', 'portal_prod_company_1'),
                    ('portal_prod_control', 'portal_test_company_1')):
                with self.subTest(control=control, tenant=tenant), self.assertRaises(RuntimeError):
                    portal.validate_postgresql_database_names(control, tenant)

    def test_production_role_split_denies_cross_plane_access(self):
        class FakeConnection:
            def __init__(self, role, access):
                self.role, self.access = role, access

            def execute(self, sql):
                return SimpleNamespace(fetchone=lambda: (self.role,) if 'current_user' in sql and
                                       'has_table_privilege' not in sql else self.access)

        control = FakeConnection('control', (True, True, False))
        tenant = FakeConnection('tenant', (True, False, False))
        portal.validate_postgresql_runtime_split(control, tenant)
        for bad_control, bad_tenant in (
                (FakeConnection('tenant', control.access), tenant),
                (FakeConnection('control', (True, True, True)), tenant),
                (control, FakeConnection('tenant', (True, True, False))),
                (control, FakeConnection('tenant', (True, False, True))),
                (control, FakeConnection('tenant', (False, False, False)))):
            with self.subTest(control=bad_control.access, tenant=bad_tenant.access), self.assertRaises(RuntimeError):
                portal.validate_postgresql_runtime_split(bad_control, bad_tenant)


if __name__ == "__main__":
    unittest.main(verbosity=2)
