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
import unittest

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
        self.tmp = tempfile.TemporaryDirectory(prefix="portal-test-")
        self.old_db = portal.DB_PATH
        portal.DB_PATH = str(Path(self.tmp.name) / "fixture.db")
        conn = sqlite3.connect(portal.DB_PATH)
        conn.executescript(SCHEMA)
        conn.close()
        portal.ensure_schema()
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

    def request(self,path,token=None,body=None,method=None,status=200):
        headers = {"Authorization":"Bearer "+token} if token else {}
        payload = json.dumps(body).encode() if body is not None else b""
        method = method or ("POST" if body is not None else "GET")
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.http:
            with http.client.HTTPConnection("127.0.0.1",self.http.server_port,timeout=5) as conn:
                conn.request(method,path,payload,headers)
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
        for role in ("manager","accountant","shift"):
            uid=portal.save_user({"username":role,"pin":"1234","role":role})
            with portal.db() as conn:
                token=portal.create_session(conn,uid)
            self.request("/api/users",token,status=403)
            self.request("/api/admin/clients",token,{},status=403)
            self.request(f"/api/users/{self.worker_id}",token,{"role":"admin"},status=403)

    def test_personal_work_and_payroll_are_isolated(self):
        d=self.request("/api/dashboard",self.worker)["data"]
        self.assertEqual(d,{"period":"current","quantity":3.0,"salary":6.0})
        self.assertEqual(len(self.request("/api/work/mine?telegram_id=202",self.worker)["rows"]),1)
        self.assertEqual(self.request("/api/payroll/mine?telegram_id=202",self.worker)["data"]["accrued"],6)
        with portal.db() as conn:
            conn.execute("UPDATE app_users SET telegram_id=NULL WHERE id=?",(self.worker_id,))
        self.assertEqual(self.request("/api/dashboard",self.worker)["data"]["quantity"],0)
        self.assertEqual(self.request("/api/work/mine",self.worker)["rows"],[])
        self.assertEqual(self.request("/api/payroll/mine",self.worker)["data"]["accrued"],0)

    def test_user_lifecycle_revokes_old_sessions(self):
        uid=self.request("/api/users",self.admin,{"username":"new","pin":"4321","role":"packer","telegram_id":202})["id"]
        token=self.login("new","4321")["token"]
        self.request(f"/api/users/{uid}",self.admin,{"role":"shift","pin":"9876","telegram_id":101})
        self.request("/api/me",token,status=401)
        self.login("new","4321",401)
        new=self.login("new","9876")
        self.assertEqual(new["user"]["role"],"shift")
        self.assertEqual(new["user"]["telegram_id"],101)
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
        self.request("/api/work",self.worker,{"client_id":self.cid,"operation_id":self.oid,"quantity":2,"telegram_id":202})
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
