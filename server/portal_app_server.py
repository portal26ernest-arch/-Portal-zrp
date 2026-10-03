#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import sys
from decimal import Decimal
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import portal_tenancy as tenants
from production_repository import Repository
from production_service import Production
from employee_identity import (account_directory, assigned_client_ids, canonical_user_payload,
    create_employee_card, create_invited_account, employee_exists, employee_id_for_user,
    employee_work_summary, insert_unlinked_user, legacy_employee_id, legacy_employee_id_for_user,
    insert_legacy_work_values, legacy_paid_period, personal_payroll_totals, personal_work_rows, public_user_record,
    hash_access_pin, update_legacy_job_progress, write_user_account)
import production_permissions as business_rights
from production_migrations import migrate as migrate_production
from client_names import persist_client_alias, persist_known_client_aliases
from employee_names import persist_known_employee_aliases
import production_activity as activity
from portal_config import load_config
from pathlib import Path
from login_throttle import LoginLimiter, client_ip
from session_security import storage_key, migrate_tokens, revoke_sessions, authentication_lock
import documents_api
import excel_import
from document_domain import LocalFileStorage

BUILD_ID = "PORTAL Server · 4.7.0"
CONFIG = load_config(os.environ)
DB_PATH = CONFIG.sqlite_path
tenants.configure(CONFIG)
HOST = CONFIG.host
PORT = CONFIG.port
SESSION_HOURS = 24 * 30
LOGIN_LIMITER = LoginLimiter()
# Deployment must list only proxies that overwrite X-Real-IP, never arbitrary peers.
TRUSTED_LOGIN_PROXIES = tuple(value.strip() for value in os.environ.get('PORTAL_TRUSTED_LOGIN_PROXIES','').split(',') if value.strip())
GLOBAL_ROLE = "platform_owner"
GLOBAL_ROLE_LABEL = "God"

ROLE_LABELS = {
    "admin": "Управляющий",
    "director": "Директор",
    "manager": "Менеджер",
    "accountant": "Бухгалтер",
    "shift": "Старший смены",
    "packer": "Упаковщик",
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    return tenants.tenant_connection(DB_PATH)


def table_exists(conn, name):
    if CONFIG.backend == 'postgresql':
        from portal_postgres import table_exists as pg_table_exists
        return pg_table_exists(conn, name)
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def columns(conn, table):
    if CONFIG.backend == 'postgresql':
        from portal_postgres import columns as pg_columns
        return set(pg_columns(conn, table.strip('"')))
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def validate_postgresql_database_names(control_database, tenant_database):
    if CONFIG.environment == 'test' and (
            not control_database.startswith('portal_test_')
            or not tenant_database.startswith('portal_test_')):
        raise RuntimeError('Test runtime accepts only portal_test_ PostgreSQL databases')
    if CONFIG.environment == 'production' and (
            control_database == tenant_database
            or control_database.startswith('portal_test_')
            or tenant_database.startswith('portal_test_')):
        raise RuntimeError('Production requires separate non-test control and tenant databases')


def validate_postgresql_runtime_split(registry, conn):
    """Production roles must be distinct and confined to their own data plane."""
    control_role = registry.execute('SELECT current_user').fetchone()[0]
    tenant_role = conn.execute('SELECT current_user').fetchone()[0]
    if control_role == tenant_role:
        raise RuntimeError('Production control and tenant roles must differ')
    control_access = registry.execute("""SELECT
        has_table_privilege(current_user,'public.companies','SELECT'),
        has_table_privilege(current_user,'public.portal_company_keys','SELECT'),
        has_table_privilege(current_user,'public.app_users','SELECT')""").fetchone()
    tenant_access = conn.execute("""SELECT
        has_table_privilege(current_user,'public.app_users','SELECT'),
        has_table_privilege(current_user,'public.companies','SELECT'),
        has_table_privilege(current_user,'public.portal_company_keys','SELECT')""").fetchone()
    if control_access != (True, True, False) or tenant_access != (True, False, False):
        raise RuntimeError('Production PostgreSQL roles cross the control/tenant boundary')


def ensure_schema(require_session_storage=True):
    if CONFIG.backend == 'postgresql':
        from portal_postgres import validate_runtime_role
        if CONFIG.host not in ('127.0.0.1', '::1'):
            raise RuntimeError('PostgreSQL API must bind to loopback')
        with tenants.control(DB_PATH) as registry, tenants.company_scope(1), db() as conn:
            validate_runtime_role(registry)
            validate_runtime_role(conn)
            control_database = registry.execute('SELECT current_database()').fetchone()[0]
            tenant_database = conn.execute('SELECT current_database()').fetchone()[0]
            validate_postgresql_database_names(control_database, tenant_database)
            if CONFIG.environment == 'production':
                validate_postgresql_runtime_split(registry, conn)
            required = {'companies','app_users','app_sessions','portal_clients','portal_client_operations',
                        'work_log','employees','portal_production','portal_production_migrations',
                        'work_material_consumption','portal_runtime_schema','portal_rls_context_schema',
                        'backup_log','client_access','client_invites','client_invoice_items',
                        'client_name_overrides','client_permissions','employee_access_requests',
                        'employee_chat_messages','employee_chat_settings','employee_invites',
                        'expense_requests','managers','marketplace_news','payroll_closure_batches',
                        'payroll_settlement_entries','payroll_employee_identities',
                        'portal_client_requisites','portal_company_requisites',
                        'portal_manager_service_rates','production_job_assignments','products',
                        'scheduled_runs','system_settings','tariff_versions','user_roles'}
            missing = sorted(name for name in required if not table_exists(conn if name not in {'companies'} else registry, name))
            if (missing
                    or not conn.execute('SELECT 1 FROM portal_runtime_schema WHERE version=1').fetchone()
                    or not conn.execute('SELECT 1 FROM portal_rls_context_schema WHERE version=1').fetchone()
                    or not conn.execute('SELECT 1 FROM portal_production_migrations WHERE version=6').fetchone()
                    or (require_session_storage and not conn.execute('SELECT 1 FROM portal_production_migrations WHERE company_id=1 AND version=15').fetchone())):
                raise RuntimeError('PostgreSQL runtime schema is incomplete: ' + ', '.join(missing))
            rls_required = required - {'companies','portal_runtime_schema','portal_rls_context_schema'}
            placeholders = ','.join('?' for _ in rls_required)
            checks = conn.execute(
                f"SELECT count(*),count(*) FILTER (WHERE relrowsecurity AND relforcerowsecurity) "
                f"FROM pg_class WHERE relname IN ({placeholders})", tuple(sorted(rls_required))
            ).fetchone()
            if checks != (len(rls_required), len(rls_required)):
                raise RuntimeError('Required PostgreSQL company RLS is not forced')
            from production_migrations import validate_payroll_settlement
            validate_payroll_settlement(Repository(conn,1))
            triggers = conn.execute("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('production_immutable','production_batch_number_immutable','portal_no_delete')").fetchone()[0]
            if triggers < 10:
                raise RuntimeError('PostgreSQL history triggers are incomplete')
            retention = conn.execute(
                "SELECT pg_get_functiondef('portal_production_immutable()'::regprocedure)"
            ).fetchone()[0]
            if not all(kind in retention for kind in ('chat_messages','chat_pins','chat_attachments')):
                raise RuntimeError('PostgreSQL chat retention schema is incomplete')
        return
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"База PORTAL не найдена: {DB_PATH}")
    with tenants.connect_file(DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        required = {"portal_clients", "portal_client_operations", "work_log", "employees"}
        missing = [t for t in required if not table_exists(conn, t)]
        if missing:
            raise RuntimeError("Требуется проверенный импорт исходных данных PORTAL. Нет таблиц: " + ", ".join(missing))
        statements = """
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
        """
        for statement in statements.split(";"):
            if statement.strip():
                conn.execute(statement)
        tenants.stamp_schema(conn, 1)
        migrate_tokens(conn,1)
    tenants.initialize_control(DB_PATH)


def runtime_ready():
    """Check both data planes without returning data or connection details."""
    with tenants.control(DB_PATH) as registry:
        if registry.execute('SELECT 1 FROM companies WHERE id=1').fetchone() is None:
            return False
    with tenants.company_scope(1), db() as conn:
        if CONFIG.backend == 'postgresql':
            return bool(
                conn.execute('SELECT portal_current_company()').fetchone()[0] == 1
                and conn.execute('SELECT 1 FROM portal_runtime_schema WHERE version=1').fetchone()
                and conn.execute('SELECT 1 FROM portal_rls_context_schema WHERE version=1').fetchone()
            )
        return table_exists(conn, 'app_users') and table_exists(conn, 'work_log')


def hash_pin(pin, salt=None):
    return hash_access_pin(pin,salt)


def verify_pin(pin, salt, expected):
    _, actual = hash_pin(pin, salt)
    return hmac.compare_digest(actual, expected)


def create_session(conn, user_id):
    token = str(tenants.COMPANY_ID.get()) + "." + secrets.token_urlsafe(40)
    created = datetime.now()
    expires = created + timedelta(hours=SESSION_HOURS)
    revoke_sessions(conn,tenants.COMPANY_ID.get(),before=now_text(),reason='expired')
    conn.execute(
        "INSERT INTO app_sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
        (storage_key(token), user_id, created.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return token


def user_from_token(token):
    if not token:
        return None
    if token.startswith("p."):
        with tenants.control(DB_PATH) as conn:
            row = conn.execute("SELECT u.id,u.username,u.display_name,u.company_id FROM platform_sessions s JOIN platform_owners u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>=? AND u.active=1",
                               (hashlib.sha256(token.encode()).hexdigest(), now_text())).fetchone()
        return dict(row, role=GLOBAL_ROLE) if row else None
    try:
        company_id = int(token.split(".", 1)[0]) if "." in token else 1
        company = tenants.get_company(DB_PATH, company_id)
    except (ValueError, PermissionError):
        return None
    if not tenants.available(company):
        return None
    with tenants.company_scope(company_id), db() as conn:
        row = conn.execute("""
            SELECT u.* FROM app_sessions s JOIN app_users u ON u.id=s.user_id
            WHERE s.token=? AND s.expires_at>=? AND u.active=1
        """, (storage_key(token), now_text())).fetchone()
        return with_employee_id(row,conn,company_id) if row and row["role"] in ROLE_LABELS else None


def with_employee_id(row, connection=None, company_id=None):
    if row is None:return None
    data=dict(row)
    if connection is not None:
        data['employee_id']=employee_id_for_user(connection,company_id,data)
    elif 'employee_id' not in data:
        # Callers without tenant DB context must not invent a canonical identity.
        data['employee_id']=None
    return data


def save_user_from_api(body, user_id=None):
    """Canonical API boundary; retained legacy IDs stay behind the storage adapter."""
    with db() as conn:body=canonical_user_payload(conn,tenants.COMPANY_ID.get(),body)
    return save_user(body,user_id)


def require_role(user, allowed):
    return user and user.get("role") in allowed


def business_can(user, permission, legacy_roles):
    with db() as conn:
        repo = Repository(conn, tenants.COMPANY_ID.get())
        if repo.ready(): return permission in business_rights.effective(repo,user)
    return user['role'] in legacy_roles


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
    return assigned_client_ids(conn,tenants.COMPANY_ID.get(),user.get('employee_id'))


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
    return legacy_paid_period(conn,tenants.COMPANY_ID.get(),worker_id,s.strftime("%Y-%m-%d %H:%M:%S"),e.strftime("%Y-%m-%d %H:%M:%S"))


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
        if CONFIG.backend == 'postgresql':
            conn.execute("""
                INSERT INTO work_material_consumption(work_id,material_id,quantity,unit_cost,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(company_id,work_id,material_id)
                DO UPDATE SET quantity=EXCLUDED.quantity,unit_cost=EXCLUDED.unit_cost,updated_at=EXCLUDED.updated_at
            """, (work_id, n[0], consume, float(n[6] or 0), now_text()))
        else:
            conn.execute("""
                INSERT OR REPLACE INTO work_material_consumption(work_id,material_id,quantity,unit_cost,updated_at)
                VALUES(?,?,?,?,?)
            """, (work_id, n[0], consume, float(n[6] or 0), now_text()))
        stock = float(n[4] or 0) - consume
        if stock <= float(n[5] or 0):
            warnings.append(f"{n[2]}: осталось {stock:g} {n[3]}")
    return warnings


def sync_production(conn, work_id, employee_id, client_name, operation_name, product_name, quantity):
    if not table_exists(conn, "production_jobs"):
        return
    jobs = conn.execute("""
        SELECT j.id,j.target_quantity,COALESCE(SUM(p.quantity),0) done
        FROM production_jobs j LEFT JOIN production_job_progress p ON p.job_id=j.id AND p.company_id=j.company_id
        WHERE j.client=? AND j.operation=? AND j.status IN ('open','in_progress')
          AND (? IS NULL OR j.product_name IS NULL OR j.product_name='' OR j.product_name=?)
        GROUP BY j.company_id,j.id ORDER BY j.priority DESC, COALESCE(j.due_at,'9999-12-31'),j.id
    """, (client_name, operation_name, product_name, product_name)).fetchall()
    update_legacy_job_progress(conn,CONFIG.backend,tenants.COMPANY_ID.get(),jobs,work_id,employee_id,quantity,now_text(),client_name,operation_name,product_name)


def save_work(user, client_id, operation_id, quantity):
    if user["role"] not in {"admin","director","manager","shift","packer"}:
        raise PermissionError("Эта роль не может вносить выработку")
    worker_employee_id = user.get("employee_id")
    if worker_employee_id is None:
        raise ValueError("Пользователь приложения не привязан к сотруднику PORTAL")
    qty = int(quantity)
    if qty <= 0 or qty > 1000000:
        raise ValueError("Количество должно быть от 1 до 1 000 000")
    with db() as conn:
        worker_id=legacy_employee_id_for_user(conn,tenants.COMPANY_ID.get(),user)
        if worker_id is None:raise ValueError("Канонический ID не связан с карточкой сотрудника этой компании")
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
        if paid_period(conn, worker_employee_id, created):
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
        values = {
            "employee_id": worker_employee_id, "username": user["username"], "first_name": first_name,
            "client": c["name"], "operation": op["name"], "quantity": qty, "rate": rate,
            "salary": salary, "created_at": created, "updated_at": None,
            "product_id": product_id, "product_name": product_name, "client_rate": client_rate,
            "revenue": revenue, "unit_direct_cost": unit_direct, "direct_cost": direct,
            "tariff_version_id": tariff[0] if tariff else None, "anomaly_flag": 0,
        }
        wid=insert_legacy_work_values(conn,CONFIG.backend,tenants.COMPANY_ID.get(),worker_employee_id,values)
        warnings=sync_materials(conn,wid,int(op["id"]),qty,worker_id)
        sync_production(conn,wid,worker_employee_id,c["name"],op["name"],product_name,qty)
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
        if user["role"]=="packer":
            w=employee_work_summary(conn,tenants.COMPANY_ID.get(),user.get('employee_id'),start,end)
        elif user["role"] == "manager":
            allowed=manager_allowed_client_ids(conn,user) or set()
            if allowed:
                worker_filter=" AND client IN (SELECT name FROM portal_clients WHERE id IN ("+','.join('?' for _ in allowed)+"))"
                params.extend(sorted(allowed))
            else:
                worker_filter=' AND 1=0'
        if user['role']!='packer':
            row=conn.execute(f"""
                SELECT COALESCE(SUM(quantity),0) qty,COALESCE(SUM(salary),0) salary,
                       COALESCE(SUM(revenue),0) revenue,COALESCE(SUM(direct_cost),0) direct_cost
                FROM work_log WHERE created_at BETWEEN ? AND ? {worker_filter}
            """,params).fetchone()
            w=dict(zip(('qty','salary','revenue','direct_cost'),row))
        invoiced=paid=debt=0.0
        if user["role"] in {"admin","director","manager","accountant"} and table_exists(conn,"client_invoices"):
            allowed=manager_allowed_client_ids(conn,user)
            inv=conn.execute("SELECT id,client,amount_due FROM client_invoices WHERE created_at BETWEEN ? AND ?",(start,end)).fetchall()
            if allowed is not None:
                names={r["name"]:int(r["id"]) for r in conn.execute("SELECT id,name FROM portal_clients").fetchall()}
                inv=[r for r in inv if names.get(r["client"]) in allowed]
            for r in inv:
                invoiced+=float(r["amount_due"] or 0)
                p=conn.execute("SELECT COALESCE(SUM(amount),0) FROM client_payments WHERE invoice_id=?",(r["id"],)).fetchone()[0]
                paid+=float(p or 0); debt+=max(float(r["amount_due"] or 0)-float(p or 0),0)
        if user["role"] == "packer":
            return {"period":period,"quantity":float(w["qty"] or 0),"salary":float(w["salary"] or 0)}
        profit=float(w["revenue"] or 0)-float(w["salary"] or 0)-float(w["direct_cost"] or 0)
        return {"period":period,"quantity":float(w["qty"] or 0),"salary":float(w["salary"] or 0),"revenue":float(w["revenue"] or 0),"direct_cost":float(w["direct_cost"] or 0),"profit":profit,"invoiced":invoiced,"paid":paid,"debt":debt}


def clean_name(value, label="Название"):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        raise ValueError(f"{label}: от 1 до 200 символов")
    return value.strip()


def active_value(value):
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ValueError("Активность должна быть 0 или 1")
    return int(value)


def rate_value(value):
    try:
        rate = float(value)
    except (ValueError, TypeError):
        raise ValueError("Ставка должна быть числом")
    if isinstance(value, bool) or not math.isfinite(rate) or rate < 0 or rate > 1000000000:
        raise ValueError("Ставка должна быть от 0 до 1 000 000 000")
    return rate


def validate_employee(conn, value):
    try:
        employee_id = int(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        raise ValueError("Выберите сотрудника PORTAL")
    if employee_id is not None and not employee_exists(conn,tenants.COMPANY_ID.get(),employee_id):
        raise ValueError("Сотрудник PORTAL не найден")
    return employee_id


def create_internal_employee(conn, display_name, username):
    company_id=tenants.COMPANY_ID.get()
    employee_id=create_employee_card(conn,company_id,display_name,username)
    repo=Repository(conn,company_id)
    if repo.ready():persist_known_employee_aliases(repo,employee_id,display_name)
    return employee_id


def save_user(body, user_id=None):
    with db() as identity_conn:
        body=canonical_user_payload(identity_conn,tenants.COMPANY_ID.get(),body,allow_legacy_bridge=True)
    if "company_id" in body and body["company_id"] != tenants.COMPANY_ID.get():
        raise PermissionError("Нельзя менять компанию доступа")
    if user_id is not None and user_id <= 0:
        raise ValueError("Некорректный ID доступа")
    # Serialize limits with platform company changes as well as user activation.
    with tenants.control(DB_PATH) as registry, db() as conn:
        registry.execute("BEGIN IMMEDIATE")
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM app_users WHERE id=?", (user_id,)).fetchone() if user_id else None
        if user_id and not old:
            raise ValueError("Доступ не найден")
        values = dict(old) if old else {"role": "packer", "employee_id": None, "active": 1}
        if old:values['employee_id']=employee_id_for_user(conn,tenants.COMPANY_ID.get(),old)
        values.update({k: body[k] for k in ("username", "display_name", "role", "employee_id", "active") if k in body})
        username = clean_name(values.get("username"), "Логин")
        display = clean_name(values.get("display_name") or username, "Имя")
        role = values["role"]
        if not isinstance(role, str) or role not in ROLE_LABELS:
            raise ValueError("Неизвестная роль")
        active = active_value(values["active"])
        limit = registry.execute("SELECT user_limit FROM companies WHERE id=?", (tenants.COMPANY_ID.get(),)).fetchone()[0]
        if active and (not old or not old["active"]) and limit is not None:
            count = conn.execute("SELECT COUNT(*) FROM app_users WHERE active=1").fetchone()[0]
            if count >= limit:
                raise ValueError("Достигнут лимит активных пользователей компании")
        employee = validate_employee(conn, values.get("employee_id"))
        if conn.execute("SELECT 1 FROM app_users WHERE lower(username)=lower(?) AND id!=?", (username, user_id or 0)).fetchone():
            raise ValueError("Этот логин уже занят")
        if old and old["role"] == "admin" and old["active"] and (role != "admin" or not active):
            if not conn.execute("SELECT 1 FROM app_users WHERE role='admin' AND active=1 AND id!=?", (user_id,)).fetchone():
                raise ValueError("Нельзя отключить последнего администратора или изменить его роль")
        pin = body.get("pin")
        if pin is not None or not old:
            if not isinstance(pin, str) or not 4 <= len(pin) <= 128:
                raise ValueError("PIN должен содержать от 4 до 128 символов")
            salt, digest = hash_pin(pin)
        else:
            salt, digest = old["pin_salt"], old["pin_hash"]
        create_employee = body.get("create_employee", True if not old and employee is None else False)
        if type(create_employee) is not bool:
            raise ValueError("Некорректный режим создания сотрудника")
        if not old and employee is None:
            if not create_employee:
                raise ValueError("Для доступа существующего сотрудника выберите его карточку")
            employee = create_internal_employee(conn, display, username)
        if role == "packer" and employee is None:
            raise ValueError("Упаковщик должен иметь собственную карточку сотрудника")
        values.update(username=username,display_name=display,role=role,active=active,employee_id=employee)
        user_id=write_user_account(conn,tenants.COMPANY_ID.get(),user_id,values,salt,digest,now_text())
        repo=Repository(conn,tenants.COMPANY_ID.get())
        if repo.has_table('payroll_employee_identities'):
            repo.sync_payroll_employees()
        return user_id


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def rename_references(conn, old_name, new_name, client=None, client_id=None):
    # The BOT uses text names in its ledger as well as numeric catalogue IDs.
    # Rename those links atomically; quantities, money and IDs remain untouched.
    if CONFIG.backend == 'postgresql':
        from portal_postgres import table_names
        tables = table_names(conn)
    else:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for table in tables:
        cols = columns(conn, quote_identifier(table))
        quoted = quote_identifier(table)
        if client is None and "client" in cols:
            conn.execute(f"UPDATE {quoted} SET client=? WHERE client=?", (new_name, old_name))
        elif client is not None and "operation" in cols:
            if "client" in cols:
                conn.execute(f"UPDATE {quoted} SET operation=? WHERE operation=? AND client=?", (new_name, old_name, client))
            elif "client_id" in cols:
                conn.execute(f"UPDATE {quoted} SET operation=? WHERE operation=? AND client_id=?", (new_name, old_name, client_id))


def write_catalogue(conn, table, values, item_id=None):
    available = columns(conn, table)
    values = {k: v for k, v in values.items() if k in available}
    if "updated_at" in available:
        values["updated_at"] = now_text()
    if item_id is not None:
        conn.execute(f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(), item_id))
        return item_id
    if "created_at" in available:
        values["created_at"] = now_text()
    return conn.execute(f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})", tuple(values.values())).lastrowid


def save_client(body, client_id=None, actor_id=None):
    if client_id is not None and client_id <= 0:
        raise ValueError("Некорректный ID клиента")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = get_client(conn, client_id) if client_id else None
        if client_id and not old:
            raise ValueError("Клиент не найден")
        name = clean_name(body.get("name", old["name"] if old else None))
        active = active_value(body.get("active", old["active"] if old else 1))
        if conn.execute("SELECT 1 FROM portal_clients WHERE name=? COLLATE NOCASE AND id!=?", (name, client_id or 0)).fetchone():
            raise ValueError("Клиент с таким названием уже существует (включая архив)")
        repo=Repository(conn,tenants.COMPANY_ID.get())
        renamed=bool(old and name != old["name"])
        if renamed:
            if repo.ready():
                repo.insert('client_name_history',dict(client_id=int(client_id),old_name=old['name'],
                    new_name=name,event='renamed',actor_id=actor_id,occurred_at=now_text()))
                repo.audit({'id':actor_id},'client.renamed',client_id)
            else:
                # Keep the legacy name-based compatibility path only before
                # the stable-ID production ledger is enabled for this tenant.
                rename_references(conn, old["name"], name)
        saved_id=write_catalogue(conn, "portal_clients", {"name": name, "active": active}, client_id)
        if repo.ready():
            if renamed: persist_client_alias(repo,int(saved_id),old["name"],'rename',name)
            persist_known_client_aliases(repo,int(saved_id),name)
        return saved_id


def save_operation(body, client_id, operation_id=None):
    if operation_id is not None and operation_id <= 0:
        raise ValueError("Некорректный ID работы")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        client = get_client(conn, client_id)
        if not client:
            raise ValueError("Клиент не найден")
        old = conn.execute("SELECT * FROM portal_client_operations WHERE id=? AND client_id=?", (operation_id, client_id)).fetchone() if operation_id else None
        if operation_id and not old:
            raise ValueError("Работа не найдена у этого клиента")
        name = clean_name(body.get("name", old["name"] if old else None))
        values = {"name": name, "active": active_value(body.get("active", old["active"] if old else 1))}
        for field in ("employee_rate", "client_rate"):
            if field in body or not old:
                values[field] = rate_value(body.get(field))
        if conn.execute("SELECT 1 FROM portal_client_operations WHERE client_id=? AND name=? COLLATE NOCASE AND id!=?", (client_id, name, operation_id or 0)).fetchone():
            raise ValueError("Работа с таким названием у клиента уже существует")
        if old and name != old["name"]:
            rename_references(conn, old["name"], name, client["name"], client_id)
        if not old:
            values.update(client_id=client_id, sort_order=0)
        identity = write_catalogue(conn, "portal_client_operations", values, operation_id)
        repo = Repository(conn, tenants.COMPANY_ID.get())
        if repo.ready() and any(k in values for k in ('employee_rate','client_rate')):
            from production_service import cents
            repo.insert('tariffs', dict(operation_id=identity, client_id=client_id, effective_from=__import__('production_repository').utcnow(),
                changed_fields=[k for k in ('employee_rate','client_rate') if k in values],
                employee_rate=cents(values.get('employee_rate',old['employee_rate'] if old else 0)),
                client_rate=cents(values.get('client_rate',old['client_rate'] if old else 0))))
        return identity


def read_body(handler):
    if handler.headers.get("Transfer-Encoding"):
        raise ValueError("Требуется Content-Length")
    length = int(handler.headers.get("Content-Length", "0") or 0)
    path = urlparse(getattr(handler, "path", "")).path
    file_routes={'/api/v3/documents','/api/v3/document-upload','/api/v3/excel-import-preview','/api/v3/excel-import-apply'}
    limit = 14 * 1024 * 1024 if path in file_routes else 3 * 1024 * 1024 if path == "/api/v3/chat" else 65536
    if not 0 <= length <= limit:
        label = "14 МБ" if limit>3*1024*1024 else "3 МБ" if limit > 65536 else "64 КБ"
        raise ValueError("Размер запроса должен быть не более " + label)
    return handler.rfile.read(length) if length else b""


def parse_body(handler):
    raw = handler.raw_body if hasattr(handler, "raw_body") else read_body(handler)
    settlement=urlparse(getattr(handler,'path','')).path=='/api/v3/payroll-settlements'
    def invalid_constant(value):
        raise ValueError('В расчёте недопустимы бесконечность и неопределённые числа')
    try:
        # Financial decimals retain their exact JSON spelling before Decimal parsing.
        body = json.loads(raw.decode('utf-8'),parse_float=str,parse_constant=invalid_constant) if raw and settlement else (json.loads(raw.decode('utf-8')) if raw else {})
    except (UnicodeError,json.JSONDecodeError):
        if settlement:raise ValueError('Некорректный JSON расчёта зарплаты') from None
        raise
    if not isinstance(body, dict):
        raise ValueError("Ожидается JSON-объект")
    if 'telegram_id' in body:
        raise ValueError('Используйте employee_id')
    if getattr(handler, "tenant_request", False) and "company_id" in body:
        if type(body["company_id"]) is not int or body["company_id"] != tenants.COMPANY_ID.get():
            raise PermissionError("Компания определяется авторизованной сессией")
    return body


def create_platform_owner(username, pin, display_name=None):
    """Local operator provisioning only. No HTTP route promotes company users."""
    username = clean_name(username, "Логин")
    if not isinstance(pin, str) or not 12 <= len(pin) <= 128:
        raise ValueError("Пароль Platform Owner: от 12 до 128 символов")
    salt, digest = hash_pin(pin)
    with tenants.control(DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner_id = conn.execute("INSERT INTO platform_owners(username,display_name,pin_salt,pin_hash) VALUES(?,?,?,?)",
                                (username, clean_name(display_name or username), salt, digest)).lastrowid
        tenants.audit(conn, owner_id, 1, "owner_provisioned_locally", "success", entity_id=owner_id)
    return owner_id


def audit_route(path):
    """A fixed route label, not a raw URL that could carry secrets."""
    parts = path.strip("/").split("/")
    known = {"api", "platform", "companies", "audit", "me", "company", "dashboard", "clients", "admin",
             "operations", "work", "mine", "payroll", "materials", "jobs", "invoices", "users", "login",
             "v3", "invitations"}
    if any(p not in known and not p.isdecimal() for p in parts):
        return "unknown"
    return "/" + "/".join("{id}" if p.isdecimal() else p for p in parts)


def company_module_for_route(path):
    """Return the company module that protects an API route, if any."""
    if path.startswith('/api/v3/'):
        action=path.removeprefix('/api/v3/').split('/',1)[0]
        mapping={
            'work':'work','timers':'work','links':'work',
            'payroll':'payroll','payroll-mine':'payroll','payroll-periods':'payrollPeriods',
            'payroll-settlements':'payrollPeriods',
            'chat':'teamChat','chat-attachments':'teamChat','chat-pins':'teamChat',
            'clients':'clients','catalogue':'clients','operations':'clients','products':'clients','client-requisites':'clients','client-name-history':'clients','client-aliases':'clients',
            'materials':'materials','usage':'materials',
            'invoices':'invoices','invoice-template':'invoices','invoice-import-preview':'invoices','payments':'invoices','receivables':'invoices',
            'users':'users','invitations':'users','company-access':'users','presence':'users','activity':'users','audit':'users','employee-name-history':'users','employee-aliases':'users',
            'tasks':'jobs','batches':'batches','shipments':'batches','returns':'batches',
            'permissions':'permissions','tariffs':'tariffs','finance':'radar','expenses':'expenses',
            'analytics':'analytics','settings':'control','documents':'documents',
            'document-file':'documents','document-metadata':'documents','document-history':'documents','document-upload':'documents',
            'document-archive':'documents','document-generate':'documents','document-template':'excelImport',
            'document-template-blank':'excelImport','document-template-info':'excelImport',
            'excel-import-preview':'excelImport','excel-import-apply':'excelImport','excel-import-result':'excelImport',
            'marketplace-news':'news'
        }
        return mapping.get(action)
    legacy={
        '/api/work':'work','/api/work/mine':'work','/api/payroll':'payroll','/api/payroll/mine':'payroll',
        '/api/invoices':'invoices','/api/clients':'clients','/api/materials':'materials','/api/users':'users',
        '/api/jobs':'jobs','/api/admin':'clients'
    }
    for prefix,module in legacy.items():
        if path==prefix or path.startswith(prefix+'/'):
            return module
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "PORTALAppServer/1.0"

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler normally logs the raw URL, including its query.
        sys.stdout.write("[%s] %s %s\n" % (datetime.now().strftime("%H:%M:%S"), self.command, audit_route(urlparse(self.path).path)))

    def send_json(self, data, status=200, headers=None):
        self.response_status = status
        raw=json.dumps(data,ensure_ascii=False,default=lambda value: float(value) if isinstance(value,Decimal) else str(value)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        for name,value in (headers or {}).items():self.send_header(name,str(value))
        self.end_headers(); self.wfile.write(raw)

    def error_json(self, message, status=400):
        self.send_json({"ok":False,"error":str(message)},status)

    def login_budget(self,key,limit=10,window=900):
        retry=LOGIN_LIMITER.consume(key,limit,window)
        if retry:
            self.send_json({'ok':False,'error':'Слишком много попыток. Повторите позже.','retry_after':retry},
                           429,headers={'Retry-After':retry})
        return not retry

    def token(self):
        auth=self.headers.get("Authorization","")
        if auth.startswith("Bearer "): return auth[7:].strip()
        return self.headers.get("X-Portal-Token","").strip()

    def current_user(self):
        return getattr(self, "request_user", None) or user_from_token(self.token())

    def do_GET(self):
        web_path = urlparse(self.path).path
        if web_path == "/web" or web_path.startswith("/web/"):
            from web_static import serve
            return serve(self)
        try: self.route("GET")
        except PermissionError as e: self.error_json(e,403)
        except ValueError as e: self.error_json(e,400)
        except Exception as e:
            self.error_json("Внутренняя ошибка сервера",500)

    def do_POST(self):
        try:
            # Consume bounded request bytes even on authorization failures, so
            # closing an HTTP/1.0 connection does not discard its error response.
            self.raw_body = read_body(self)
            self.route("POST")
        except PermissionError as e: self.error_json(e,403)
        except ValueError as e: self.error_json(e,400)
        except sqlite3.IntegrityError: self.error_json("Запись конфликтует с существующими данными",400)
        except Exception as e:
            self.error_json("Внутренняя ошибка сервера",500)

    def route(self, method):
        self.tenant_request = False
        path = urlparse(self.path).path
        readonly_preview=path=='/api/v3/excel-import-preview'
        if method=='POST' and path in ('/api/login','/api/platform/login','/api/me/pin'):
            peer=client_ip(self.client_address[0],self.headers,TRUSTED_LOGIN_PROXIES)
            if not self.login_budget(('ip',peer),limit=60,window=60):return
        if path == '/api/desktop-update':
            if method != 'GET':
                return self.error_json('Метод не поддерживается', 405)
            import desktop_update
            manifest = desktop_update.load_manifest(os.environ)
            if manifest is None:
                return self.error_json('Канал обновлений Desktop не настроен', 404)
            return self.send_json({'ok': True, **manifest})
        if path == '/api/access-invites/accept' and method == 'POST':
            # The invitation token is the only bearer value accepted here. PIN is
            # read from the bounded POST body and is never accepted from a URL.
            body=parse_body(self)
            if set(body)!={'token','pin'}:
                raise ValueError('Ожидаются только token и PIN')
            import re
            token=body.get('token')
            match=re.match(r'^([1-9][0-9]{0,17})\.',token) if isinstance(token,str) else None
            if not match: raise PermissionError('Приглашение недействительно')
            company_id=int(match.group(1))
            selected=self.headers.get('X-Portal-Company')
            if selected is not None and selected!=str(company_id):
                raise PermissionError('Компания приглашения не совпадает с выбранной')
            company=tenants.get_company(DB_PATH,company_id)
            if not tenants.available(company): raise PermissionError('Компания недоступна')
            with tenants.company_scope(company_id),db() as conn:
                repo=Repository(conn,company_id)
                if not repo.ready() or not repo.has_table('portal_access_invites') or not conn.execute('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=10',(company_id,)).fetchone():
                    raise PermissionError('Приглашение недействительно')
                repo.lock()
                import access_invites
                result=access_invites.accept(conn,repo,token,body.get('pin'))
                conn.commit()
            return self.send_json({'ok':True,'data':result})
        if path == "/api/platform/login" and method == "POST":
            body = parse_body(self)
            with tenants.control(DB_PATH) as conn:
                u = conn.execute("SELECT * FROM platform_owners WHERE username=? AND active=1", (str(body.get("username", "")),)).fetchone()
                principal=('platform',u['id']) if u else ('platform_unknown',hashlib.sha256(str(body.get('username','')).strip().lower().encode()).hexdigest())
                if not self.login_budget(principal):return
                valid = bool(u and verify_pin(str(body.get("pin", "")), u["pin_salt"], u["pin_hash"]))
                if u:
                    tenants.audit(conn, u["id"], 1, "god_login", "success" if valid else "denied")
                if valid:
                    token = "p." + secrets.token_urlsafe(40)
                    conn.execute("INSERT INTO platform_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                                 (hashlib.sha256(token.encode()).hexdigest(), u["id"], (datetime.now()+timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")))
                    result = {"ok":True,"token":token,"user":{"id":u["id"],"username":u["username"],"role":GLOBAL_ROLE,"company_id":1}}
            return self.send_json(result) if valid else self.error_json("Неверный логин или пароль", 401)
        if path == "/api/login" and method == "POST":
            body = parse_body(self)
            company_id = body.get("company_id", 1)
            if type(company_id) is not int or company_id < 1:
                return self.error_json("Неверный логин, PIN или компания", 401)
            try:
                company = tenants.get_company(DB_PATH, company_id)
            except PermissionError:
                return self.error_json("Неверный логин, PIN или компания", 401)
            if not tenants.available(company):
                return self.error_json("Компания недоступна", 403)
            username=str(body.get("username", "")).strip()
            pin=str(body.get("pin", ""))
            with tenants.company_scope(company_id), db() as conn:
                authentication_lock(conn)
                u = conn.execute("SELECT * FROM app_users WHERE lower(username)=lower(?) AND active=1", (username,)).fetchone()
                if u:
                    if not self.login_budget(('tenant',company_id,u['id'])):return
                    if not verify_pin(pin, u["pin_salt"], u["pin_hash"]):
                        repo=Repository(conn,company_id)
                        if repo.ready():activity.login(repo,u['username'],u['id'],False,activity.client_type(self.headers))
                        return self.error_json("Неверный логин, PIN или компания", 401)
                    token = create_session(conn, u["id"])
                    repo=Repository(conn,company_id)
                    if repo.ready():activity.login(repo,u['username'],u['id'],True,activity.client_type(self.headers),token)
                    data = public_user_record({k:v for k,v in with_employee_id(u,conn,company_id).items() if k not in {"pin_hash","pin_salt"}})
                    return self.send_json({"ok":True,"token":token,"user":data})
            with tenants.control(DB_PATH) as control:
                god = control.execute("SELECT * FROM platform_owners WHERE lower(username)=lower(?) AND active=1", (username,)).fetchone()
                if god:
                    if not self.login_budget(('platform',god['id'])):return
                    valid=verify_pin(pin,god["pin_salt"],god["pin_hash"])
                    tenants.audit(control,god["id"],1,"god_login","success" if valid else "denied")
                    if not valid:
                        return self.error_json("Неверный логин, PIN или компания",401)
                    token="p."+secrets.token_urlsafe(40)
                    control.execute("INSERT INTO platform_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                                    (hashlib.sha256(token.encode()).hexdigest(),god["id"],(datetime.now()+timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")))
                    return self.send_json({"ok":True,"token":token,"user":{"id":god["id"],"username":god["username"],"role":GLOBAL_ROLE,"company_id":1}})
            principal=('tenant_unknown',company_id,hashlib.sha256(username.lower().encode()).hexdigest())
            if not self.login_budget(principal):return
            return self.error_json("Неверный логин, PIN или компания",401)
        if path == '/api/ready':
            if method != 'GET':
                return self.error_json('Метод не поддерживается', 405)
            try:
                ready = runtime_ready()
            except Exception:
                ready = False
            return self.send_json({'ok': True, 'ready': True}) if ready else self.error_json('Сервис не готов', 503)
        if path in {"/api/ping", "/api/setup"}:
            with tenants.company_scope(1):
                self.tenant_request = True
                return self.tenant_route(method)
        identity = user_from_token(self.token())
        if not identity:
            return self.error_json("Требуется вход", 401)
        is_owner = identity["role"] == GLOBAL_ROLE
        company_id = identity["company_id"]
        if path=='/api/logout' and method=='POST':
            if is_owner:
                with tenants.control(DB_PATH) as conn:
                    conn.execute('DELETE FROM platform_sessions WHERE token_hash=?',(hashlib.sha256(self.token().encode()).hexdigest(),))
                    tenants.audit(conn,identity['id'],1,'god_logout','success')
            else:
                with tenants.company_scope(company_id),db() as conn:
                    activity.logout(Repository(conn,company_id),self.token(),identity)
            return self.send_json({'ok':True})
        if is_owner and not readonly_preview:
            with tenants.control(DB_PATH) as conn:
                tenants.audit(conn, identity["id"], company_id, "god_access", "started", method=method, route=audit_route(path))
        try:
            selected = self.headers.get("X-Portal-Company")
            if selected is not None:
                try:
                    selected = int(selected)
                except ValueError:
                    raise PermissionError("Некорректная компания")
                if not is_owner and selected != company_id:
                    raise PermissionError("Доступ к другой компании запрещён")
                if is_owner:
                    tenants.get_company(DB_PATH, selected)
                    company_id = selected
            if not is_owner:
                if path.startswith("/api/platform/"):
                    raise PermissionError("Раздел недоступен")
                query = parse_qs(urlparse(self.path).query)
                if "company_id" in query and query["company_id"] != [str(company_id)]:
                    raise PermissionError("Доступ к другой компании запрещён")
                if not tenants.available(tenants.get_company(DB_PATH,company_id)):
                    raise PermissionError('Компания недоступна')
            if path.startswith("/api/platform/"):
                return self.platform_route(method, path, identity)
            if path == "/api/me" and method == "GET":
                safe = public_user_record({k:v for k,v in identity.items() if k not in {"pin_salt","pin_hash"}})
                safe["role_label"] = GLOBAL_ROLE_LABEL if is_owner else ROLE_LABELS.get(identity["role"], identity["role"])
                if not is_owner:
                    with tenants.company_scope(company_id), db() as conn:
                        repo=Repository(conn,company_id)
                        if repo.ready(): safe['permissions']=sorted(business_rights.effective(repo,identity))
                return self.send_json({"ok":True,"user":safe})
            if path == "/api/me/pin" and method == "POST":
                if is_owner:
                    raise PermissionError("Для этого аккаунта используется отдельный пароль")
                body=parse_body(self)
                if set(body)!={'current_pin','new_pin'}:
                    raise ValueError("Передайте текущий и новый PIN")
                current_pin=body.get('current_pin')
                new_pin=body.get('new_pin')
                if not isinstance(current_pin,str) or not isinstance(new_pin,str):
                    raise ValueError("PIN должен быть строкой")
                if not 4<=len(new_pin)<=128:
                    raise ValueError("Новый PIN должен содержать от 4 до 128 символов")
                if current_pin==new_pin:
                    raise ValueError("Новый PIN должен отличаться от текущего")
                if not self.login_budget(('tenant',company_id,identity['id'])):return
                with tenants.company_scope(company_id), db() as conn:
                    authentication_lock(conn)
                    account=conn.execute("SELECT id,pin_salt,pin_hash FROM app_users WHERE id=? AND active=1",(identity['id'],)).fetchone()
                    if not account or not verify_pin(current_pin,account['pin_salt'],account['pin_hash']):
                        raise ValueError("Текущий PIN указан неверно")
                    salt,digest=hash_pin(new_pin)
                    conn.execute("UPDATE app_users SET pin_salt=?,pin_hash=?,updated_at=? WHERE id=?",
                                 (salt,digest,now_text(),identity['id']))
                    revoke_sessions(conn,company_id,user_id=identity['id'],keep_token=self.token(),
                                    reason='pin_changed',actor_id=identity['id'])
                    repo=Repository(conn,company_id)
                    if repo.ready():repo.audit(identity,'user.pin.changed',identity['id'])
                    conn.commit()
                return self.send_json({"ok":True})
            if is_owner and selected is None:
                raise PermissionError("Выберите компанию для глобального доступа")
            module=company_module_for_route(path)
            if module and tenants.decode_module_toggles(tenants.get_company(DB_PATH,company_id).get('module_toggles')).get(module) is False:
                raise PermissionError('Модуль отключён для компании')
            with tenants.company_scope(company_id):
                self.tenant_request = True
                self.request_user = dict(identity, role="admin", company_id=company_id, employee_id=None, technical_owner=True) if is_owner else identity
                if not is_owner and not readonly_preview:
                    with db() as conn:activity.touch(Repository(conn,company_id),self.token(),identity)
                if path.startswith('/api/v3/'):
                    return self.production_route(method,path)
                if path == "/api/company" and method == "GET":
                    company = tenants.get_company(DB_PATH, company_id)
                    if not is_owner and identity["role"] not in {"admin", "director"}:
                        company = {k: company[k] for k in ("id", "name", "status", "service_status")}
                    return self.send_json({"ok":True,"company":company})
                return self.tenant_route(method)
        except PermissionError:
            self.response_status = 403
            raise
        except (ValueError, sqlite3.IntegrityError):
            self.response_status = 400
            raise
        finally:
            if is_owner and not readonly_preview:
                status = getattr(self, "response_status", 500)
                with tenants.control(DB_PATH) as conn:
                    numeric_ids = [int(p) for p in path.split("/") if p.isdecimal() and len(p) < 19]
                    tenants.audit(conn, identity["id"], company_id, "god_access", "success" if status < 400 else "failed",
                                  method=method, route=audit_route(path), status=status, entity_id=numeric_ids)

    def production_route(self,method,path):
        action=path.removeprefix('/api/v3/')
        with db() as conn:
            repo=Repository(conn,tenants.COMPANY_ID.get())
            if action=='meta' and method=='GET':
                ready=bool(repo.ready())
                company=tenants.get_company(DB_PATH,repo.company_id)
                company_sync={key:company[key] for key in ('id','name','status','service_status','module_toggles')}
                return self.send_json(dict(ok=True,ready=ready,
                    permissions=sorted(business_rights.effective(repo,self.request_user)) if ready else [],
                    catalog=business_rights.public_catalog(),
                    heartbeat_seconds=activity.configuration(repo)[0] if ready else None,
                    company=company_sync,server_time=now_text()))
            if not repo.ready(): raise ValueError('Этап 3 ещё не подключён оператором к этой компании')
            if action=='company-access' and method=='GET':
                service=Production(repo,self.request_user);service.need_management_role()
                if not ({'users.manage','company.settings'}&service.permissions):raise PermissionError('Недостаточно прав для настроек компании')
                company=tenants.get_company(DB_PATH,repo.company_id)
                active=conn.execute('SELECT COUNT(*) FROM app_users WHERE active=1').fetchone()[0]
                return self.send_json({'ok':True,'data':{'active_users':active,'user_limit':company['user_limit'],'unlimited':company['user_limit'] is None}})
            if action=='invitations' and (not repo.has_table('portal_access_invites') or not conn.execute('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=10',(repo.company_id,)).fetchone()):
                raise ValueError('Безопасные приглашения ещё не подключены оператором к этой компании')
            if action=='invitations':
                import access_invites
                service=Production(repo,self.request_user);service.need_management_role()
                service.need('users.manage')
                if method=='GET':
                    query=parse_qs(urlparse(self.path).query)
                    page=int(query.get('page',['1'])[0]);limit=int(query.get('limit',['50'])[0]);status=query.get('status',['all'])[0]
                    return self.send_json({'ok':True,'data':access_invites.list_invites(conn,repo.company_id,page,limit,status)})
                if method!='POST': raise ValueError('Метод приглашений не поддерживается')
                body=parse_body(self); action_type=body.get('action')
                repo.lock()
                if action_type=='create':
                    role=body.get('role','packer')
                    if role not in business_rights.ROLE_NAMES or business_rights.defaults(role)-service.permissions:
                        raise PermissionError('Нельзя пригласить сотрудника с более широкими правами')
                    result=access_invites.create(conn,repo,self.request_user,body,repo.company_id)
                elif action_type in ('approve','revoke','reject'):
                    identity=body.get('invite_id')
                    if not isinstance(identity,str) or len(identity)>128: raise ValueError('Некорректное приглашение')
                    if action_type=='approve': conn.commit()
                    result=access_invites.decide(conn,repo,self.request_user,identity,action_type)
                else: raise ValueError('Неизвестное действие приглашения')
                conn.commit()
                return self.send_json({'ok':True,'data':result})
            if action=='audit' and method=='GET':
                service=Production(repo,self.request_user);service.need_management_role()
                service.need('users.manage')
                query=parse_qs(urlparse(self.path).query)
                def number(key,default,minimum,maximum):
                    try:value=int(query.get(key,[str(default)])[0])
                    except (TypeError,ValueError):raise ValueError('Некорректный фильтр аудита')
                    if not minimum<=value<=maximum:raise ValueError('Некорректный фильтр аудита')
                    return value
                page=number('page',1,1,10000);limit=number('limit',50,1,100)
                actor=query.get('actor_id',[''])[0];event=query.get('action',[''])[0];entity=query.get('entity_id',[''])[0]
                start=query.get('from',[''])[0];end=query.get('to',[''])[0]
                import re,json
                if actor and not actor.isdecimal():raise ValueError('Некорректный фильтр пользователя')
                for value in (start,end):
                    if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Дата аудита должна быть YYYY-MM-DD')
                if start and end and start>end:raise ValueError('Начальная дата позже конечной')
                users={str(u['id']):u.get('display_name','') for u in repo.catalog('users')}
                rows=conn.execute("SELECT id,payload,created_at FROM portal_production WHERE company_id=? AND kind='audit' ORDER BY created_at DESC,id DESC",(repo.company_id,)).fetchall()
                items=[]
                labels={'access_invite.created':'Создано приглашение','access_invite.accepted':'Принят запрос доступа','access_invite.approved':'Подтверждён доступ','access_invite.revoked':'Приглашение отозвано','access_invite.rejected':'Запрос отклонён','access_invite.expired':'Приглашение истекло','client.requisites.updated':'Обновлены реквизиты клиента','user.permissions.updated':'Изменены права сотрудника','user.pin.changed':'Сотрудник сменил PIN','company.settings.updated':'Изменены настройки компании'}
                for row in rows:
                    payload=json.loads(row['payload']);at=row['created_at'][:10];actor_id=payload.get('actor_id')
                    if not self.request_user.get('technical_owner') and payload.get('actor_kind')=='platform_owner':continue
                    if actor and str(actor_id)!=actor:continue
                    if event and payload.get('event')!=event:continue
                    if entity and str(payload.get('entity_id'))!=entity:continue
                    if start and at<start or end and at>end:continue
                    items.append({'id':row['id'],'at':row['created_at'],'actor_id':actor_id,'actor_name':users.get(str(actor_id),'Система/получатель' if actor_id is None else 'Сотрудник'),
                        'action':payload.get('event','event'),'entity_id':payload.get('entity_id'),
                        'summary':labels.get(payload.get('event'),'Изменение в системе')})
                offset=(page-1)*limit
                return self.send_json({'ok':True,'data':{'items':items[offset:offset+limit],'page':page,'limit':limit,'total':len(items)}})
            if action in excel_import.IMPORT_ACTIONS:
                if not repo.has_table('portal_excel_imports'):raise ValueError('Сначала примените миграцию Documents/Excel')
                service=Production(repo,self.request_user)
                storage=LocalFileStorage(os.environ.get('PORTAL_DOCUMENT_ROOT',str(Path(DB_PATH).resolve().parent/'.portal-documents')))
                importer=excel_import.ExcelImport(service,storage,tenants.get_company(DB_PATH,repo.company_id))
                if action=='excel-import-preview' and method=='POST':
                    return self.send_json(dict(ok=True,data=importer.preview(parse_body(self))))
                if action=='excel-import-apply' and method=='POST':
                    from excel_apply import apply_import
                    repo.lock();result=apply_import(importer,parse_body(self));conn.commit()
                    if result['status']=='failed':
                        return self.send_json(dict(ok=False,error='Импорт отменён полностью; см. отчёт',data=result),409)
                    return self.send_json(dict(ok=True,data=result))
                if action=='excel-import-result' and method=='GET':
                    from excel_apply import import_result
                    return self.send_json(dict(ok=True,data=import_result(importer,parse_qs(urlparse(self.path).query).get('id',[None])[0])))
                raise ValueError('Метод импорта не поддерживается')
            if action=='payroll-settlements' and (not repo.has_table('payroll_settlement_entries') or
                    not conn.execute('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=6',(repo.company_id,)).fetchone()):
                raise ValueError('Реестр расчётов зарплаты ещё не подключён оператором к этой компании')
            if action=='presence' and method=='GET':return self.send_json(dict(ok=True,data=activity.presence(repo,self.request_user)))
            if action=='activity' and method=='GET':
                limit=int(parse_qs(urlparse(self.path).query).get('limit',['100'])[0])
                return self.send_json(dict(ok=True,data=activity.history(repo,self.request_user,limit)))
            if action=='heartbeat' and method=='POST':
                if self.request_user.get('technical_owner'):
                    return self.send_json(dict(ok=True))
                session=activity.touch(repo,self.token(),self.request_user,True)
                conn.commit()
                return self.send_json(dict(ok=True,last_activity_at=session['last_activity_at'] if session else None))
            if action=='marketplace-news' and method=='GET':
                service=Production(repo,self.request_user)
                if not {'chat.read','clients.read','tasks.read'} & service.permissions:raise PermissionError('Недостаточно прав для чтения новостей')
                query=parse_qs(urlparse(self.path).query)
                source=query.get('source',['all'])[0]
                if source not in ('all','ozon','wildberries'):raise ValueError('Фильтр source должен быть all, ozon или wildberries')
                try:limit=max(1,min(100,int(query.get('limit',['30'])[0])));offset=max(0,int(query.get('offset',['0'])[0]))
                except (ValueError,TypeError):raise ValueError('Некорректная пагинация')
                where='company_id=?';args=[repo.company_id]
                if source!='all':where+=' AND source=?';args.append(source)
                rows=conn.execute('SELECT source,title,body,published_at,url,is_regulation FROM marketplace_news WHERE '+where+' ORDER BY published_at DESC NULLS LAST,id DESC LIMIT ? OFFSET ?',tuple(args+[limit,offset])).fetchall()
                from marketplace_news import canonical_url
                names=('source','title','body','published_at','url','is_regulation');items=[]
                for row in rows:
                    item=dict(zip(names,row));item['body']=(item['body'] or '')[:600]
                    try:item['url']=canonical_url(item['source'],item['url'])
                    except ValueError:item['url']=None
                    items.append(item)
                return self.send_json(dict(ok=True,data=items,next_offset=offset+len(rows) if len(rows)==limit else None))
            if action in ('invoice-template','invoice-import-preview'):
                import invoice_exchange
                service=Production(repo,self.request_user)
                if action=='invoice-template' and method=='GET':
                    query=parse_qs(urlparse(self.path).query)
                    try:client_id=int(query.get('client_id',[''])[0])
                    except (TypeError,ValueError):raise ValueError('Выберите клиента')
                    return self.send_json(dict(ok=True,data=invoice_exchange.template(service,client_id)))
                if action=='invoice-import-preview' and method=='POST':
                    return self.send_json(dict(ok=True,data=invoice_exchange.preview(service,parse_body(self))))
                raise ValueError('Метод обмена Excel счёта не поддерживается')
            if (action in documents_api.DOCUMENT_ACTIONS and repo.has_table('portal_documents')) or action in documents_api.TEMPLATE_ACTIONS:
                if method=='POST':repo.lock()
                service=Production(repo,self.request_user)
                storage=LocalFileStorage(os.environ.get('PORTAL_DOCUMENT_ROOT',str(Path(DB_PATH).resolve().parent/'.portal-documents')))
                values=parse_body(self) if method=='POST' else parse_qs(urlparse(self.path).query)
                if action in documents_api.TEMPLATE_ACTIONS:
                    result=documents_api.template_route(service,storage,action,method,values,tenants.get_company(DB_PATH,repo.company_id))
                else:result=documents_api.route(service,storage,action,method,values,tenants.get_company(DB_PATH,repo.company_id))
                if method=='POST':conn.commit()
                return self.send_json(dict(ok=True,data=result))
            if method=='POST':repo.lock()
            service=Production(repo,self.request_user)
            if method=='POST':
                body=parse_body(self)
            else:
                body=None
            if action=='payroll-settlements' and method=='GET':
                query=parse_qs(urlparse(self.path).query)
                if 'telegram_id' in query:raise ValueError('Используйте employee_id')
                result=service.query(action,query)
            else:
                result=service.command(action,body) if method=='POST' else service.query(action,parse_qs(urlparse(self.path).query))
            # Commit before acknowledging any write.
            if method=='POST':conn.commit()
            return self.send_json(dict(ok=True,data=result))

    def platform_route(self, method, path, identity):
        if identity["role"] != GLOBAL_ROLE:
            raise PermissionError("Раздел недоступен")
        if path == "/api/platform/companies":
            if method == "GET":
                with tenants.control(DB_PATH) as conn:
                    companies = [tenants.company_from_row(r) for r in conn.execute("SELECT * FROM companies ORDER BY id")]
                return self.send_json({"ok":True,"companies":companies})
            return self.send_json({"ok":True,"id":tenants.save_company(DB_PATH, identity["id"], parse_body(self))})
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:3] == ["api", "platform", "companies"]:
            cid = int(parts[3])
            if method == "GET":
                return self.send_json({"ok":True,"company":tenants.get_company(DB_PATH, cid)})
            return self.send_json({"ok":True,"id":tenants.save_company(DB_PATH, identity["id"], parse_body(self), cid)})
        if path == "/api/platform/audit" and method == "GET":
            query = parse_qs(urlparse(self.path).query)
            def audit_int(key,default,minimum,maximum):
                try:value=int(query.get(key,[str(default)])[0])
                except (TypeError,ValueError):raise ValueError('Некорректный фильтр аудита')
                if not minimum<=value<=maximum:raise ValueError('Некорректный фильтр аудита')
                return value
            page=audit_int('page',1,1,10000);limit=audit_int('limit',50,1,100)
            conditions=[];args=[]
            if query.get('company_id',[''])[0]:conditions.append('company_id=?');args.append(audit_int('company_id',1,1,10**18))
            if query.get('actor_id',[''])[0]:conditions.append('actor_id=?');args.append(audit_int('actor_id',1,1,10**18))
            if query.get('event',[''])[0]:conditions.append('event=?');args.append(query['event'][0][:80])
            start=query.get('from',[''])[0];end=query.get('to',[''])[0]
            import re
            if any(v and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v) for v in (start,end)) or start and end and start>end:raise ValueError('Некорректный диапазон дат аудита')
            if start:conditions.append('substr(created_at,1,10)>=?');args.append(start)
            if end:conditions.append('substr(created_at,1,10)<=?');args.append(end)
            where=(' WHERE '+' AND '.join(conditions)) if conditions else ''
            with tenants.control(DB_PATH) as conn:
                total=conn.execute('SELECT COUNT(*) FROM platform_audit'+where,tuple(args)).fetchone()[0]
                rows = [dict(r) for r in conn.execute("SELECT * FROM platform_audit"+where+" ORDER BY id DESC LIMIT ? OFFSET ?",tuple(args+[limit,(page-1)*limit]))]
            aliases={"owner_login":"god_login","owner_logout":"god_logout","technical_access":"god_access"}
            for row in rows: row["event"]=aliases.get(row["event"],row["event"])
            return self.send_json({"ok":True,"rows":rows,"page":page,"limit":limit,"total":total})
        return self.error_json("Маршрут не найден", 404)

    def tenant_route(self, method):
        parsed=urlparse(self.path); path=parsed.path; qs=parse_qs(parsed.query)
        if path=="/api/ping" and method=="GET":
            with db() as conn:
                count=conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
            return self.send_json({"ok":True,"build":BUILD_ID,"setup_required":count==0})
        if path=="/api/setup" and method=="POST":
            if self.client_address[0] not in {"127.0.0.1", "::1"}:
                raise PermissionError("Первого администратора создайте на телефоне сервера через 127.0.0.1")
            body=parse_body(self); username=(body.get("username") or "admin").strip(); name=(body.get("display_name") or "Администратор").strip(); pin=str(body.get("pin") or "")
            if len(pin)<4: raise ValueError("PIN должен содержать минимум 4 символа")
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]>0: raise PermissionError("Первичная настройка уже выполнена")
                salt,ph=hash_pin(pin)
                # APK/desktop accounts are independent from the retired Telegram identity.
                # An employee card can be linked explicitly later by a company administrator.
                user_id=insert_unlinked_user(conn,username,name,salt,ph,now_text())
                token=create_session(conn,user_id); conn.commit()
            return self.send_json({"ok":True,"token":token,"user":{"username":username,"display_name":name,"role":"admin","employee_id":None}})
        user=self.current_user()
        if not user: return self.error_json("Требуется вход",401)
        with db() as connection:
            repo=Repository(connection,tenants.COMPANY_ID.get())
            production_ready=repo.ready()
            permissions=business_rights.effective(repo,user) if production_ready else None
        if production_ready:
            needed={'/api/work':'work.write','/api/payroll/mine':'payroll.own','/api/work/mine':'work.write','/api/materials':'materials.read','/api/invoices':'invoices.read','/api/jobs':'tasks.read','/api/users':'users.manage'}
            required=needed.get(path)
            if path.startswith('/api/users/'):required='users.manage'
            if path.startswith('/api/admin/'):required='clients.manage'
            if required and required not in permissions:raise PermissionError('Недостаточно прав')
            if path=='/api/work' and method=='POST':
                body=parse_body(self)
                with db() as connection:
                    repo=Repository(connection,tenants.COMPANY_ID.get());repo.lock()
                    body.setdefault('request_id',secrets.token_hex(24))
                    work=Production(repo,user).command('work',body);connection.commit()
                return self.send_json(dict(ok=True,work=dict(id=work['legacy_id'],salary=work.get('salary',0)/100,rate=work.get('employee_rate',0)/100,warnings=[])))
            if path.startswith('/api/users') and method=='POST':
                body=parse_body(self)
                if 'role' in body and (body['role'] not in ROLE_LABELS or business_rights.defaults(body['role'])-permissions):raise PermissionError('Нельзя назначить роль с правами выше собственных')
                if path.count('/')==3:
                    with db() as connection:
                        repo=Repository(connection,tenants.COMPANY_ID.get())
                        target=next((u for u in repo.catalog('users') if str(u['id'])==path.split('/')[-1]),None)
                        if target and business_rights.effective(repo,target)-permissions:raise PermissionError('Нельзя менять доступ сотрудника с более широкими правами')
            if path.startswith('/api/admin/') and method=='POST':
                body=parse_body(self)
                parts=path.strip('/').split('/')
                if len(parts)>=4:
                    with db() as connection:
                        if not allowed_client(connection,user,int(parts[3])):raise PermissionError('Клиент недоступен')
                for field,key in [('employee_rate','rates.employee'),('client_rate','rates.client')]:
                    if field in body and key not in permissions:raise PermissionError('Недостаточно прав для изменения цены')
        if path.startswith("/api/admin/"):
            if not business_can(user,'clients.manage',{'admin'}): raise PermissionError("Нет права управления справочником")
            parts = path.strip("/").split("/")
            if parts == ["api", "admin", "clients"]:
                if method == "GET":
                    return self.send_json({"ok":True,"clients":get_clients(user,False)})
                return self.send_json({"ok":True,"id":save_client(parse_body(self),actor_id=user['id'])})
            if len(parts) == 4 and parts[:3] == ["api", "admin", "clients"] and method == "POST":
                return self.send_json({"ok":True,"id":save_client(parse_body(self),int(parts[3]),user['id'])})
            if len(parts) in (5, 6) and parts[:3] == ["api", "admin", "clients"] and parts[4] == "operations":
                client_id = int(parts[3])
                if method == "GET" and len(parts) == 5:
                    with db() as conn:
                        client = get_client(conn,client_id)
                        if not client: raise ValueError("Клиент не найден")
                        if not allowed_client(conn,user,client_id):raise PermissionError('Клиент недоступен')
                        rows = [dict(r) for r in conn.execute("SELECT id,name,active,employee_rate,client_rate FROM portal_client_operations WHERE client_id=? ORDER BY sort_order,name",(client_id,))]
                    return self.send_json({"ok":True,"client":dict(client),"operations":rows})
                if method == "POST":
                    operation_id = int(parts[5]) if len(parts) == 6 else None
                    return self.send_json({"ok":True,"id":save_operation(parse_body(self),client_id,operation_id)})
            return self.error_json("Маршрут не найден",404)
        if path.startswith("/api/users/") and method == "POST" and path.count("/") == 3:
            if not business_can(user,'users.manage',{'admin'}): raise PermissionError("Нет права управления сотрудниками")
            return self.send_json({"ok":True,"id":save_user_from_api(parse_body(self),int(path.split("/")[3]))})
        if method == "POST" and path not in {"/api/users", "/api/work"}:
            return self.error_json("Метод не поддерживается",405)
        if path=="/api/me":
            safe=public_user_record({k:v for k,v in user.items() if k not in {"pin_hash","pin_salt"}}); safe["role_label"]=ROLE_LABELS.get(user["role"],user["role"])
            return self.send_json({"ok":True,"user":safe})
        if path=="/api/dashboard":
            if production_ready and 'finance.read' not in permissions:
                if 'payroll.own' not in permissions:return self.send_json(dict(ok=True,data={}))
                return self.send_json(dict(ok=True,data=dashboard(dict(user,role='packer'),qs.get('period',['current'])[0])))
            return self.send_json({"ok":True,"data":dashboard(user,qs.get("period",["current"])[0])})
        if path=="/api/clients":
            if production_ready and not {'clients.read','work.write','tasks.read'} & permissions:raise PermissionError('Нет доступа к клиентам')
            return self.send_json({"ok":True,"clients":get_clients(user,True)})
        if path.startswith("/api/clients/") and path.endswith("/operations"):
            client_id=int(path.split("/")[3])
            with db() as conn:
                c=allowed_client(conn,user,client_id)
                if not c or not c["active"]: raise PermissionError("Клиент недоступен")
                rows=[dict(r) for r in conn.execute("SELECT id,name,employee_rate,client_rate FROM portal_client_operations WHERE client_id=? AND active=1 ORDER BY sort_order,name",(client_id,)).fetchall()]
                if user["role"] == "packer":
                    rows = [{k:v for k,v in r.items() if k != "client_rate"} for r in rows]
                if production_ready:
                    if not {'work.write','clients.read','tasks.read'} & permissions:raise PermissionError('Нет доступа к операциям')
                    rows=[{k:v for k,v in r.items() if (k!='employee_rate' or 'payroll.own' in permissions or 'rates.employee' in permissions) and (k!='client_rate' or 'finance.read' in permissions or 'rates.client' in permissions)} for r in rows]
            return self.send_json({"ok":True,"client":dict(c),"operations":rows})
        if path.startswith("/api/clients/") and path.count("/")==3:
            if not business_can(user,'finance.read',set(ROLE_LABELS)-{'packer'}): raise PermissionError("Нет доступа к финансовой карточке клиента")
            client_id=int(path.split("/")[3])
            with db() as conn:
                c=allowed_client(conn,user,client_id)
                if not c: raise PermissionError("Клиент недоступен")
                work=conn.execute("SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(revenue),0),COALESCE(SUM(salary),0) FROM work_log WHERE client=?",(c["name"],)).fetchone()
                invoices=conn.execute("SELECT COUNT(*),COALESCE(SUM(amount_due),0) FROM client_invoices WHERE client=?",(c["name"],)).fetchone() if table_exists(conn,"client_invoices") else (0,0)
                req=conn.execute("SELECT legal_name,inn,kpp,phone,email,contact_person FROM portal_client_requisites WHERE client_id=?",(client_id,)).fetchone() if table_exists(conn,"portal_client_requisites") else None
            return self.send_json({"ok":True,"client":dict(c),"stats":{"quantity":work[0],"revenue":work[1],"salary":work[2],"invoices":invoices[0],"invoiced":invoices[1]},"requisites":dict(req) if req else {}})
        if path=="/api/work" and method=="POST":
            body=parse_body(self)
            if "employee_id" in body:
                raise ValueError("employee_id определяется авторизованной сессией")
            result=save_work(user,body.get("client_id"),body.get("operation_id"),body.get("quantity"))
            return self.send_json({"ok":True,"work":result})
        if path=="/api/work/mine":
            with db() as conn:
                rows=personal_work_rows(conn,tenants.COMPANY_ID.get(),user.get('employee_id'))
                if production_ready and 'payroll.own' not in permissions:rows=[{k:v for k,v in r.items() if k not in ('rate','salary')} for r in rows]
            return self.send_json({"ok":True,"rows":rows})
        if path=="/api/payroll/mine":
            s,e=period_bounds("current")
            with db() as conn:
                q_quantity,q_salary,paid=personal_payroll_totals(conn,tenants.COMPANY_ID.get(),user.get('employee_id'),s,e)
                q=(q_quantity,q_salary)
            return self.send_json({"ok":True,"data":{"quantity":q[0],"accrued":q[1],"paid":paid,"remaining":max(float(q[1] or 0)-float(paid or 0),0),"start":s,"end":e}})
        if path=="/api/materials":
            if not business_can(user,'materials.read',{"admin","director","shift","accountant"}): raise PermissionError("Нет доступа к складу материалов")
            with db() as conn:
                rows=[dict(r) for r in conn.execute("SELECT id,name,unit,stock_qty,min_stock,unit_cost,active FROM materials WHERE active=1 ORDER BY name").fetchall()] if table_exists(conn,"materials") else []
            return self.send_json({"ok":True,"materials":rows})
        if path=="/api/jobs":
            with db() as conn:
                rows=[dict(r) for r in conn.execute("""
                    SELECT j.*,COALESCE(SUM(p.quantity),0) done FROM production_jobs j LEFT JOIN production_job_progress p ON p.job_id=j.id AND p.company_id=j.company_id
                    WHERE j.status IN ('open','in_progress') GROUP BY j.company_id,j.id ORDER BY j.priority DESC,COALESCE(j.due_at,'9999-12-31'),j.id
                """).fetchall()] if table_exists(conn,"production_jobs") else []
                if user["role"]=="manager":
                    allowed=manager_allowed_client_ids(conn,user) or set(); names={r["name"] for r in conn.execute("SELECT id,name FROM portal_clients WHERE id IN (%s)"%(','.join('?'*len(allowed))),tuple(allowed)).fetchall()} if allowed else set(); rows=[r for r in rows if r["client"] in names]
                if user["role"] == "packer":
                    fields = {"id","client","operation","product_name","due_at","priority","target_quantity","done","status"}
                    rows = [{k:v for k,v in r.items() if k in fields} for r in rows]
            return self.send_json({"ok":True,"jobs":rows})
        if path=="/api/invoices":
            if not business_can(user,'invoices.read',{"admin","director","manager","accountant"}): raise PermissionError("Нет доступа к счетам")
            with db() as conn:
                client_filter = ""
                params = ()
                if user["role"] == "manager":
                    allowed=manager_allowed_client_ids(conn,user) or set()
                    if allowed:
                        client_filter = "WHERE i.client IN (SELECT name FROM portal_clients WHERE id IN ("+','.join('?' for _ in allowed)+"))"
                        params = tuple(sorted(allowed))
                    else:
                        client_filter='WHERE 1=0'
                rows=[dict(r) for r in conn.execute(f"""
                    SELECT i.id,i.client,i.description,i.amount_due,i.due_date,i.created_at,i.closed_at,
                           COALESCE((SELECT SUM(p.amount) FROM client_payments p WHERE p.invoice_id=i.id),0) paid
                    FROM client_invoices i {client_filter} ORDER BY i.id DESC LIMIT 100
                """,params).fetchall()]
            return self.send_json({"ok":True,"invoices":rows})
        if path=="/api/users" and method=="GET":
            if not business_can(user,'users.manage',{'admin'}): raise PermissionError("Нет права управления сотрудниками")
            with db() as conn:
                repo=Repository(conn,tenants.COMPANY_ID.get())
                rows=[]
                rows=account_directory(conn,tenants.COMPANY_ID.get())
                employees=repo.employee_catalog()
            return self.send_json({"ok":True,"users":rows,"employees":employees,"roles":ROLE_LABELS})
        if path=="/api/users" and method=="POST":
            if not business_can(user,'users.manage',{'admin'}): raise PermissionError("Нет права управления сотрудниками")
            return self.send_json({"ok":True,"id":save_user_from_api(parse_body(self))})
        return self.error_json("Маршрут не найден",404)


def main():
    import argparse
    import getpass
    parser = argparse.ArgumentParser(description="PORTAL company API server")
    parser.add_argument("--create-platform-owner", metavar="USERNAME", help="Создать технический доступ локально, с интерактивным вводом пароля")
    parser.add_argument('--migrate-stage3',type=int,metavar='COMPANY_ID',help='Явно подключить производственный учёт к проверенной копии БД компании')
    args = parser.parse_args()
    if args.migrate_stage3 is not None and args.migrate_stage3<1:
        parser.error('COMPANY_ID must be positive')
    ensure_schema(require_session_storage=args.migrate_stage3 is None)
    if args.migrate_stage3 is not None:
        with tenants.company_scope(args.migrate_stage3), db() as conn:
            migrate_production(conn,args.migrate_stage3)
        print('Миграция Этапа 3 завершена')
        return
    if args.create_platform_owner:
        pin = getpass.getpass("Пароль Platform Owner (минимум 12 символов): ")
        if pin != getpass.getpass("Повторите пароль: "):
            raise ValueError("Пароли не совпадают")
        create_platform_owner(args.create_platform_owner, pin)
        print("Platform Owner создан. Существующие администраторы не повышались.")
        return
    print(BUILD_ID)
    print("База:", DB_PATH if CONFIG.backend == 'sqlite' else f'PostgreSQL {CONFIG.environment}')
    print(f"Сервер: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__ == "__main__":
    main()
