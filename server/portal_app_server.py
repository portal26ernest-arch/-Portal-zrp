#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BUILD_ID = "PORTAL Android Server · 2026.09.23-a001"
DEFAULT_DB = "/storage/emulated/0/PORTAL-BOT/portal.db"
DB_PATH = os.environ.get("PORTAL_DB", DEFAULT_DB)
HOST = os.environ.get("PORTAL_APP_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORTAL_APP_PORT", "8765"))
OWNER_TELEGRAM_ID = 7835466558
SESSION_HOURS = 24 * 30

ROLE_LABELS = {
    "admin": "Администратор",
    "manager": "Менеджер",
    "accountant": "Бухгалтер",
    "shift": "Старший смены",
    "packer": "Упаковщик",
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"База PORTAL не найдена: {DB_PATH}")
    with db() as conn:
        required = {"portal_clients", "portal_client_operations", "work_log", "employees"}
        missing = [t for t in required if not table_exists(conn, t)]
        if missing:
            raise RuntimeError("База PORTAL слишком старая. Сначала запустите PORTAL BOT b005. Нет таблиц: " + ", ".join(missing))
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            pin_salt TEXT NOT NULL,
            pin_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            telegram_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS app_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES app_users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_app_sessions_user ON app_sessions(user_id, expires_at);
        """)
        conn.commit()


def hash_pin(pin, salt=None):
    salt_b = base64.b64decode(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt_b, 180000)
    return base64.b64encode(salt_b).decode(), base64.b64encode(digest).decode()


def verify_pin(pin, salt, expected):
    _, actual = hash_pin(pin, salt)
    return hmac.compare_digest(actual, expected)


def create_session(conn, user_id):
    token = secrets.token_urlsafe(40)
    created = datetime.now()
    expires = created + timedelta(hours=SESSION_HOURS)
    conn.execute("DELETE FROM app_sessions WHERE expires_at < ?", (now_text(),))
    conn.execute(
        "INSERT INTO app_sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
        (token, user_id, created.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return token


def user_from_token(token):
    if not token:
        return None
    with db() as conn:
        row = conn.execute("""
            SELECT u.* FROM app_sessions s JOIN app_users u ON u.id=s.user_id
            WHERE s.token=? AND s.expires_at>=? AND u.active=1
        """, (token, now_text())).fetchone()
        return dict(row) if row else None


def require_role(user, allowed):
    return user and user.get("role") in allowed


def period_bounds(kind="current"):
    now = datetime.now()
    if kind == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif kind == "7d":
        start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif kind == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        if now.day <= 15:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(day=15, hour=23, minute=59, second=59, microsecond=0)
        else:
            import calendar
            last = calendar.monthrange(now.year, now.month)[1]
            start = now.replace(day=16, hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(day=last, hour=23, minute=59, second=59, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def manager_allowed_client_ids(conn, user):
    if user["role"] != "manager":
        return None
    tg = user.get("telegram_id")
    if not tg:
        return set()
    rows = conn.execute("SELECT client_id FROM manager_client_assignments WHERE telegram_id=? AND active=1", (tg,)).fetchall()
    return {int(r[0]) for r in rows}


def get_clients(user, active_only=True):
    with db() as conn:
        sql = "SELECT id,name,active FROM portal_clients"
        params = []
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name COLLATE NOCASE"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        allowed = manager_allowed_client_ids(conn, user)
        if allowed is not None:
            rows = [r for r in rows if int(r["id"]) in allowed]
        return rows


def get_client(conn, client_id):
    return conn.execute("SELECT id,name,active FROM portal_clients WHERE id=?", (int(client_id),)).fetchone()


def allowed_client(conn, user, client_id):
    row = get_client(conn, client_id)
    if not row:
        return None
    allowed = manager_allowed_client_ids(conn, user)
    if allowed is not None and int(client_id) not in allowed:
        return None
    return row


def current_product(conn, client_name):
    if not table_exists(conn, "products"):
        return None
    return conn.execute("""
        SELECT id,name,COALESCE(material_cost_per_unit,0),COALESCE(other_cost_per_unit,0)
        FROM products WHERE client=? AND active=1
        ORDER BY CASE WHEN name='Общий / без товара' THEN 0 ELSE 1 END, id LIMIT 1
    """, (client_name,)).fetchone()


def paid_period(conn, worker_id, created):
    dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
    if dt.day <= 15:
        s = dt.replace(day=1, hour=0, minute=0, second=0)
        e = dt.replace(day=15, hour=23, minute=59, second=59)
    else:
        import calendar
        last = calendar.monthrange(dt.year, dt.month)[1]
        s = dt.replace(day=16, hour=0, minute=0, second=0)
        e = dt.replace(day=last, hour=23, minute=59, second=59)
    row = conn.execute("""
        SELECT 1 FROM payroll_payments WHERE telegram_id=? AND period_start=? AND period_end=? AND status='paid'
    """, (worker_id, s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S"))).fetchone()
    return bool(row)


def sync_materials(conn, work_id, operation_id, quantity, actor_id):
    if not (table_exists(conn, "operation_material_norms") and table_exists(conn, "materials")):
        return []
    norms = conn.execute("""
        SELECT n.material_id,n.qty_per_unit,m.name,m.unit,m.stock_qty,m.min_stock,m.unit_cost
        FROM operation_material_norms n JOIN materials m ON m.id=n.material_id
        WHERE n.operation_id=? AND n.active=1 AND m.active=1
    """, (operation_id,)).fetchall()
    warnings=[]
    for n in norms:
        consume = float(n[1]) * float(quantity)
        if consume <= 0: continue
        conn.execute("UPDATE materials SET stock_qty=stock_qty-?,updated_at=? WHERE id=?", (consume, now_text(), n[0]))
        conn.execute("""
            INSERT INTO material_movements(material_id,qty_change,unit_cost,movement_type,reference_type,reference_id,note,created_at,created_by)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (n[0], -consume, float(n[6] or 0), "work", "work_log", str(work_id), "PORTAL Android: автосписание", now_text(), actor_id))
        conn.execute("""
            INSERT OR REPLACE INTO work_material_consumption(work_id,material_id,quantity,unit_cost,updated_at)
            VALUES(?,?,?,?,?)
        """, (work_id, n[0], consume, float(n[6] or 0), now_text()))
        stock = float(n[4] or 0) - consume
        if stock <= float(n[5] or 0):
            warnings.append(f"{n[2]}: осталось {stock:g} {n[3]}")
    return warnings


def sync_production(conn, work_id, worker_id, client_name, operation_name, product_name, quantity):
    if not table_exists(conn, "production_jobs"):
        return
    remaining = float(quantity)
    jobs = conn.execute("""
        SELECT j.id,j.target_quantity,COALESCE(SUM(p.quantity),0) done
        FROM production_jobs j LEFT JOIN production_job_progress p ON p.job_id=j.id
        WHERE j.client=? AND j.operation=? AND j.status IN ('open','in_progress')
          AND (? IS NULL OR j.product_name IS NULL OR j.product_name='' OR j.product_name=?)
        GROUP BY j.id ORDER BY j.priority DESC, COALESCE(j.due_at,'9999-12-31'),j.id
    """, (client_name, operation_name, product_name, product_name)).fetchall()
    for j in jobs:
        if remaining <= 1e-9: break
        capacity=max(float(j[1])-float(j[2]),0)
        if capacity<=0: continue
        add=min(capacity,remaining)
        conn.execute("""
            INSERT OR IGNORE INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at)
            VALUES(?,?,?,?,?)
        """, (j[0],work_id,worker_id,add,now_text()))
        conn.execute("UPDATE production_jobs SET status='in_progress',updated_at=? WHERE id=? AND status='open'", (now_text(),j[0]))
        remaining-=add
        new_done=float(j[2])+add
        if new_done+1e-9>=float(j[1]):
            conn.execute("UPDATE production_jobs SET status='done',completed_at=?,updated_at=? WHERE id=?", (now_text(),now_text(),j[0]))


def save_work(user, client_id, operation_id, quantity):
    if user["role"] not in {"admin","shift","packer"}:
        raise PermissionError("Эта роль не может вносить выработку")
    worker_id = user.get("telegram_id")
    if not worker_id:
        raise ValueError("Пользователь приложения не привязан к сотруднику PORTAL")
    qty = int(quantity)
    if qty <= 0 or qty > 1000000:
        raise ValueError("Количество должно быть от 1 до 1 000 000")
    with db() as conn:
        c = allowed_client(conn, user, client_id)
        if not c or not int(c["active"]):
            raise ValueError("Клиент недоступен")
        op = conn.execute("""
            SELECT id,name,employee_rate,client_rate FROM portal_client_operations
            WHERE id=? AND client_id=? AND active=1
        """, (int(operation_id), int(client_id))).fetchone()
        if not op:
            raise ValueError("Операция недоступна")
        if op["employee_rate"] is None:
            raise ValueError("Для операции не установлена ставка сотрудника")
        created = now_text()
        if paid_period(conn, worker_id, created):
            raise ValueError("Текущий расчётный период уже закрыт")
        rate = float(op["employee_rate"])
        client_rate = float(op["client_rate"]) if op["client_rate"] is not None else None
        salary = qty * rate
        product = current_product(conn, c["name"])
        product_id = product[0] if product else None
        product_name = product[1] if product else "Общий / без товара"
        unit_direct = (float(product[2]) + float(product[3])) if product else 0.0
        revenue = qty * client_rate if client_rate is not None else 0.0
        direct = qty * unit_direct
        tariff = conn.execute("""
            SELECT id FROM tariff_versions WHERE client=? AND operation=? AND valid_to IS NULL ORDER BY id DESC LIMIT 1
        """, (c["name"], op["name"])).fetchone() if table_exists(conn,"tariff_versions") else None
        first_name = user["display_name"]
        cols = columns(conn,"work_log")
        values = {
            "telegram_id": worker_id, "username": user["username"], "first_name": first_name,
            "client": c["name"], "operation": op["name"], "quantity": qty, "rate": rate,
            "salary": salary, "created_at": created, "updated_at": None,
            "product_id": product_id, "product_name": product_name, "client_rate": client_rate,
            "revenue": revenue, "unit_direct_cost": unit_direct, "direct_cost": direct,
            "tariff_version_id": tariff[0] if tariff else None, "anomaly_flag": 0,
        }
        ins_cols=[k for k in values if k in cols]
        q=",".join("?" for _ in ins_cols)
        cur=conn.execute(f"INSERT INTO work_log({','.join(ins_cols)}) VALUES({q})", [values[k] for k in ins_cols])
        wid=cur.lastrowid
        warnings=sync_materials(conn,wid,int(op["id"]),qty,worker_id)
        sync_production(conn,wid,worker_id,c["name"],op["name"],product_name,qty)
        if table_exists(conn,"audit_log"):
            conn.execute("INSERT INTO audit_log(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                         (worker_id,"android_work_saved","work_log",str(wid),json.dumps({"client":c["name"],"operation":op["name"],"quantity":qty},ensure_ascii=False),created))
        conn.commit()
        return {"id":wid,"salary":salary,"rate":rate,"warnings":warnings}


def dashboard(user, period="current"):
    start,end=period_bounds(period)
    with db() as conn:
        params=[start,end]
        worker_filter=""
        if user["role"]=="packer" and user.get("telegram_id"):
            worker_filter=" AND telegram_id=?"
            params.append(user["telegram_id"])
        w=conn.execute(f"""
            SELECT COALESCE(SUM(quantity),0) qty,COALESCE(SUM(salary),0) salary,
                   COALESCE(SUM(revenue),0) revenue,COALESCE(SUM(direct_cost),0) direct_cost
            FROM work_log WHERE created_at BETWEEN ? AND ? {worker_filter}
        """,params).fetchone()
        invoiced=paid=debt=0.0
        if user["role"] in {"admin","manager","accountant"} and table_exists(conn,"client_invoices"):
            allowed=manager_allowed_client_ids(conn,user)
            inv=conn.execute("SELECT id,client,amount_due FROM client_invoices WHERE created_at BETWEEN ? AND ?",(start,end)).fetchall()
            if allowed is not None:
                names={r["name"]:int(r["id"]) for r in conn.execute("SELECT id,name FROM portal_clients").fetchall()}
                inv=[r for r in inv if names.get(r["client"]) in allowed]
            for r in inv:
                invoiced+=float(r["amount_due"] or 0)
                p=conn.execute("SELECT COALESCE(SUM(amount),0) FROM client_payments WHERE invoice_id=?",(r["id"],)).fetchone()[0]
                paid+=float(p or 0); debt+=max(float(r["amount_due"] or 0)-float(p or 0),0)
        profit=float(w["revenue"] or 0)-float(w["salary"] or 0)-float(w["direct_cost"] or 0)
        return {"period":period,"quantity":float(w["qty"] or 0),"salary":float(w["salary"] or 0),"revenue":float(w["revenue"] or 0),"direct_cost":float(w["direct_cost"] or 0),"profit":profit,"invoiced":invoiced,"paid":paid,"debt":debt}


def parse_body(handler):
    length=int(handler.headers.get("Content-Length","0") or 0)
    if not length: return {}
    raw=handler.rfile.read(length)
    return json.loads(raw.decode("utf-8")) if raw else {}


class Handler(BaseHTTPRequestHandler):
    server_version = "PORTALAppServer/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    def send_json(self, data, status=200):
        raw=json.dumps(data,ensure_ascii=False,default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def error_json(self, message, status=400):
        self.send_json({"ok":False,"error":str(message)},status)

    def token(self):
        auth=self.headers.get("Authorization","")
        if auth.startswith("Bearer "): return auth[7:].strip()
        return self.headers.get("X-Portal-Token","").strip()

    def current_user(self):
        return user_from_token(self.token())

    def do_GET(self):
        try: self.route("GET")
        except PermissionError as e: self.error_json(e,403)
        except Exception as e:
            traceback.print_exc(); self.error_json(e,500)

    def do_POST(self):
        try: self.route("POST")
        except PermissionError as e: self.error_json(e,403)
        except ValueError as e: self.error_json(e,400)
        except Exception as e:
            traceback.print_exc(); self.error_json(e,500)

    def route(self, method):
        parsed=urlparse(self.path); path=parsed.path; qs=parse_qs(parsed.query)
        if path=="/api/ping":
            with db() as conn:
                count=conn.execute("SELECT COUNT(*) FROM app_users WHERE active=1").fetchone()[0]
            return self.send_json({"ok":True,"build":BUILD_ID,"setup_required":count==0,"db":DB_PATH})
        if path=="/api/setup" and method=="POST":
            body=parse_body(self); username=(body.get("username") or "admin").strip(); name=(body.get("display_name") or "Администратор").strip(); pin=str(body.get("pin") or "")
            if len(pin)<4: raise ValueError("PIN должен содержать минимум 4 символа")
            with db() as conn:
                if conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]>0: raise PermissionError("Первичная настройка уже выполнена")
                salt,ph=hash_pin(pin)
                tg=OWNER_TELEGRAM_ID if conn.execute("SELECT 1 FROM employees WHERE telegram_id=?",(OWNER_TELEGRAM_ID,)).fetchone() else None
                cur=conn.execute("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,telegram_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                 (username,name,salt,ph,"admin",tg,1,now_text(),now_text()))
                token=create_session(conn,cur.lastrowid); conn.commit()
            return self.send_json({"ok":True,"token":token,"user":{"username":username,"display_name":name,"role":"admin","telegram_id":tg}})
        if path=="/api/login" and method=="POST":
            body=parse_body(self); username=(body.get("username") or "").strip(); pin=str(body.get("pin") or "")
            with db() as conn:
                u=conn.execute("SELECT * FROM app_users WHERE username=? AND active=1",(username,)).fetchone()
                if not u or not verify_pin(pin,u["pin_salt"],u["pin_hash"]): return self.error_json("Неверный логин или PIN",401)
                token=create_session(conn,u["id"]); conn.commit(); data=dict(u); data.pop("pin_hash",None); data.pop("pin_salt",None)
            return self.send_json({"ok":True,"token":token,"user":data})
        user=self.current_user()
        if not user: return self.error_json("Требуется вход",401)
        if path=="/api/me":
            safe={k:v for k,v in user.items() if k not in {"pin_hash","pin_salt"}}; safe["role_label"]=ROLE_LABELS.get(user["role"],user["role"])
            return self.send_json({"ok":True,"user":safe})
        if path=="/api/dashboard":
            return self.send_json({"ok":True,"data":dashboard(user,qs.get("period",["current"])[0])})
        if path=="/api/clients":
            return self.send_json({"ok":True,"clients":get_clients(user,True)})
        if path.startswith("/api/clients/") and path.endswith("/operations"):
            client_id=int(path.split("/")[3])
            with db() as conn:
                c=allowed_client(conn,user,client_id)
                if not c: raise PermissionError("Клиент недоступен")
                rows=[dict(r) for r in conn.execute("SELECT id,name,employee_rate,client_rate FROM portal_client_operations WHERE client_id=? AND active=1 ORDER BY sort_order,name",(client_id,)).fetchall()]
            return self.send_json({"ok":True,"client":dict(c),"operations":rows})
        if path.startswith("/api/clients/") and path.count("/")==3:
            client_id=int(path.split("/")[3])
            with db() as conn:
                c=allowed_client(conn,user,client_id)
                if not c: raise PermissionError("Клиент недоступен")
                work=conn.execute("SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(revenue),0),COALESCE(SUM(salary),0) FROM work_log WHERE client=?",(c["name"],)).fetchone()
                invoices=conn.execute("SELECT COUNT(*),COALESCE(SUM(amount_due),0) FROM client_invoices WHERE client=?",(c["name"],)).fetchone() if table_exists(conn,"client_invoices") else (0,0)
                req=conn.execute("SELECT legal_name,inn,kpp,phone,email,contact_person FROM portal_client_requisites WHERE client_id=?",(client_id,)).fetchone() if table_exists(conn,"portal_client_requisites") else None
            return self.send_json({"ok":True,"client":dict(c),"stats":{"quantity":work[0],"revenue":work[1],"salary":work[2],"invoices":invoices[0],"invoiced":invoices[1]},"requisites":dict(req) if req else {}})
        if path=="/api/work" and method=="POST":
            body=parse_body(self); result=save_work(user,body.get("client_id"),body.get("operation_id"),body.get("quantity"))
            return self.send_json({"ok":True,"work":result})
        if path=="/api/work/mine":
            if not user.get("telegram_id"): return self.send_json({"ok":True,"rows":[]})
            with db() as conn:
                rows=[dict(r) for r in conn.execute("SELECT id,client,operation,quantity,rate,salary,created_at FROM work_log WHERE telegram_id=? ORDER BY id DESC LIMIT 50",(user["telegram_id"],)).fetchall()]
            return self.send_json({"ok":True,"rows":rows})
        if path=="/api/payroll/mine":
            if not user.get("telegram_id"): return self.send_json({"ok":True,"data":{"quantity":0,"accrued":0,"paid":0,"remaining":0}})
            s,e=period_bounds("current")
            with db() as conn:
                q=conn.execute("SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(salary),0) FROM work_log WHERE telegram_id=? AND created_at BETWEEN ? AND ?",(user["telegram_id"],s,e)).fetchone()
                paid=conn.execute("SELECT COALESCE(SUM(amount),0) FROM payroll_transactions WHERE telegram_id=? AND period_start=? AND period_end=?",(user["telegram_id"],s,e)).fetchone()[0] if table_exists(conn,"payroll_transactions") else 0
            return self.send_json({"ok":True,"data":{"quantity":q[0],"accrued":q[1],"paid":paid,"remaining":max(float(q[1] or 0)-float(paid or 0),0),"start":s,"end":e}})
        if path=="/api/materials":
            if user["role"] not in {"admin","shift","accountant"}: raise PermissionError("Нет доступа к складу материалов")
            with db() as conn:
                rows=[dict(r) for r in conn.execute("SELECT id,name,unit,stock_qty,min_stock,unit_cost,active FROM materials WHERE active=1 ORDER BY name").fetchall()] if table_exists(conn,"materials") else []
            return self.send_json({"ok":True,"materials":rows})
        if path=="/api/jobs":
            with db() as conn:
                rows=[dict(r) for r in conn.execute("""
                    SELECT j.*,COALESCE(SUM(p.quantity),0) done FROM production_jobs j LEFT JOIN production_job_progress p ON p.job_id=j.id
                    WHERE j.status IN ('open','in_progress') GROUP BY j.id ORDER BY j.priority DESC,COALESCE(j.due_at,'9999-12-31'),j.id
                """).fetchall()] if table_exists(conn,"production_jobs") else []
                if user["role"]=="manager":
                    allowed=manager_allowed_client_ids(conn,user) or set(); names={r["name"] for r in conn.execute("SELECT id,name FROM portal_clients WHERE id IN (%s)"%(','.join('?'*len(allowed))),tuple(allowed)).fetchall()} if allowed else set(); rows=[r for r in rows if r["client"] in names]
            return self.send_json({"ok":True,"jobs":rows})
        if path=="/api/invoices":
            if user["role"] not in {"admin","manager","accountant"}: raise PermissionError("Нет доступа к счетам")
            with db() as conn:
                rows=[dict(r) for r in conn.execute("""
                    SELECT i.id,i.client,i.description,i.amount_due,i.due_date,i.created_at,i.closed_at,
                           COALESCE((SELECT SUM(p.amount) FROM client_payments p WHERE p.invoice_id=i.id),0) paid
                    FROM client_invoices i ORDER BY i.id DESC LIMIT 100
                """).fetchall()]
                if user["role"]=="manager":
                    allowed=manager_allowed_client_ids(conn,user) or set(); cmap={r["name"]:r["id"] for r in conn.execute("SELECT id,name FROM portal_clients").fetchall()}; rows=[r for r in rows if cmap.get(r["client"]) in allowed]
            return self.send_json({"ok":True,"invoices":rows})
        if path=="/api/users" and method=="GET":
            if user["role"]!="admin": raise PermissionError("Только администратор")
            with db() as conn:
                rows=[dict(r) for r in conn.execute("SELECT id,username,display_name,role,telegram_id,active,created_at FROM app_users ORDER BY display_name").fetchall()]
                employees=[dict(r) for r in conn.execute("SELECT telegram_id,full_name,username FROM employees ORDER BY full_name").fetchall()]
            return self.send_json({"ok":True,"users":rows,"employees":employees,"roles":ROLE_LABELS})
        if path=="/api/users" and method=="POST":
            if user["role"]!="admin": raise PermissionError("Только администратор")
            body=parse_body(self); username=(body.get("username") or "").strip(); display=(body.get("display_name") or username).strip(); pin=str(body.get("pin") or ""); role=(body.get("role") or "packer").strip(); tg=body.get("telegram_id")
            if not username or len(pin)<4 or role not in ROLE_LABELS: raise ValueError("Проверьте логин, PIN и роль")
            salt,ph=hash_pin(pin)
            with db() as conn:
                cur=conn.execute("INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,telegram_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(username,display,salt,ph,role,int(tg) if tg else None,1,now_text(),now_text())); conn.commit()
            return self.send_json({"ok":True,"id":cur.lastrowid})
        return self.error_json("Маршрут не найден",404)


def main():
    ensure_schema()
    print(BUILD_ID)
    print("База:", DB_PATH)
    print(f"Сервер: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__ == "__main__":
    main()
