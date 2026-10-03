"""Company storage boundary and private platform control plane.

Legacy BOT SQL is intentionally confined to the original PORTAL database. Every
other company gets an independent database; no request can supply a file path.
"""
import json
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path


COMPANY_ID = ContextVar("portal_company_id", default=1)
COMPANY_FIELDS = {"name", "status", "monthly_price", "demo_enabled", "demo_start",
                  "demo_end", "user_limit", "service_status", "module_toggles"}
MODULE_IDS = frozenset({"work", "payroll", "payrollPeriods", "teamChat", "clients", "materials",
                        "invoices", "users", "jobs", "batches", "permissions", "tariffs", "radar",
                        "expenses", "analytics", "control", "documents", "reports", "news",
                        "excelImport", "wms", "notifications"})
_CONFIG = None


def configure(config):
    """Choose storage once, before accepting requests; never fall back on errors."""
    global _CONFIG
    _CONFIG = config


def is_postgresql():
    return _CONFIG is not None and _CONFIG.backend == 'postgresql'


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect_file(path, create=False):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + ("?mode=rwc" if create else "?mode=rw"),
                           uri=True, timeout=15, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def platform_path(root):
    return Path(root).with_name(Path(root).name + ".platform.db")


def control(root):
    if is_postgresql():
        from portal_postgres import connect, connect_pooled
        if getattr(_CONFIG, 'postgres_pool_size', 0):
            return connect_pooled(_CONFIG.control_dsn, max_size=_CONFIG.postgres_pool_size)
        return connect(_CONFIG.control_dsn)
    return connect_file(platform_path(root))


def tenant_path(root, company_id):
    if type(company_id) is not int or company_id < 1:
        raise PermissionError("Некорректная компания")
    return Path(root) if company_id == 1 else Path(root).parent / ".portal-tenants" / f"company-{company_id}.db"


@contextmanager
def company_scope(company_id):
    if type(company_id) is not int or company_id < 1:
        raise PermissionError("Некорректная компания")
    token = COMPANY_ID.set(company_id)
    try:
        yield
    finally:
        COMPANY_ID.reset(token)


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def stamp_schema(conn, company_id):
    """Run in the caller's transaction. Retain all old columns, IDs and values."""
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    for row in tables:
        name = row[0]
        if name == "portal_tenant_identity":
            continue
        cols = conn.execute(f"PRAGMA table_info({quote(name)})").fetchall()
        if not any(c[1] == "company_id" for c in cols):
            conn.execute(f"ALTER TABLE {quote(name)} ADD COLUMN company_id INTEGER NOT NULL DEFAULT {company_id} CHECK (company_id = {company_id})")
        if conn.execute(f"SELECT 1 FROM {quote(name)} WHERE company_id IS NULL OR company_id != ? LIMIT 1", (company_id,)).fetchone():
            raise RuntimeError("Обнаружены данные другой компании; миграция отменена")
        # Also guard a pre-existing company_id column that lacked constraints.
        for event in ("INSERT", "UPDATE"):
            trigger = quote(f"portal_tenant_{event.lower()}_{name}")
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS {trigger} BEFORE {event} ON {quote(name)} "
                         f"WHEN NEW.company_id IS NULL OR NEW.company_id != {company_id} "
                         "BEGIN SELECT RAISE(ABORT, 'company_id mismatch'); END")
    conn.execute(f"CREATE TABLE IF NOT EXISTS portal_tenant_identity (company_id INTEGER PRIMARY KEY CHECK(company_id={company_id}), schema_version INTEGER NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO portal_tenant_identity VALUES (?,1)", (company_id,))
    if conn.execute("SELECT company_id FROM portal_tenant_identity").fetchall()[0][0] != company_id:
        raise RuntimeError("Хранилище принадлежит другой компании")


def initialize_control(root):
    with connect_file(platform_path(root), create=True) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','archived')),
            monthly_price INTEGER NOT NULL DEFAULT 0 CHECK(monthly_price>=0),
            demo_enabled INTEGER NOT NULL DEFAULT 0 CHECK(demo_enabled IN (0,1)),
            demo_start TEXT, demo_end TEXT,
            user_limit INTEGER DEFAULT 15 CHECK(user_limit IS NULL OR user_limit>=1),
            service_status TEXT NOT NULL DEFAULT 'active' CHECK(service_status IN ('active','suspended','expired')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK(id!=1 OR user_limit IS NULL)
        );
        CREATE TABLE IF NOT EXISTS platform_owners (
            id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id) CHECK(company_id=1),
            username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS platform_sessions (
            token_hash TEXT PRIMARY KEY, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id) CHECK(company_id=1),
            user_id INTEGER NOT NULL REFERENCES platform_owners(id), expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS platform_audit (
            id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
            actor_id INTEGER REFERENCES platform_owners(id), event TEXT NOT NULL,
            outcome TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS platform_audit_no_update BEFORE UPDATE ON platform_audit
        BEGIN SELECT RAISE(ABORT,'platform audit is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS platform_audit_no_delete BEFORE DELETE ON platform_audit
        BEGIN SELECT RAISE(ABORT,'platform audit is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS platform_audit_no_replace BEFORE INSERT ON platform_audit
        WHEN EXISTS(SELECT 1 FROM platform_audit WHERE id=NEW.id)
        BEGIN SELECT RAISE(ABORT,'platform audit is append-only'); END;
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(companies)")}
        if "module_toggles" not in columns:
            conn.execute("ALTER TABLE companies ADD COLUMN module_toggles TEXT NOT NULL DEFAULT '{}'")
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO companies(id,name,user_limit,created_at,updated_at) VALUES(1,'PORTAL',NULL,?,?)", (now, now))


def get_company(root, company_id):
    with control(root) as conn:
        row = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    if row is None:
        raise PermissionError("Компания недоступна")
    return company_from_row(row)


def decode_module_toggles(value):
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise RuntimeError("Настройки модулей компании повреждены") from None
    if not isinstance(value, dict) or any(key not in MODULE_IDS or type(enabled) is not bool for key, enabled in value.items()):
        raise RuntimeError("Настройки модулей компании повреждены")
    return value


def validate_module_toggles(value):
    """Validate an owner-supplied module map as a client error, not DB corruption."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError("Некорректные настройки модулей компании") from None
    if not isinstance(value, dict) or any(key not in MODULE_IDS or type(enabled) is not bool for key, enabled in value.items()):
        raise ValueError("Некорректные настройки модулей компании")
    return value


def company_from_row(row):
    value = dict(row)
    value["module_toggles"] = decode_module_toggles(value.get("module_toggles"))
    return value


def available(company):
    if company["status"] != "active" or company["service_status"] != "active":
        return False
    if company["demo_enabled"]:
        now = datetime.now().isoformat(timespec="seconds")
        return company["demo_start"] <= now <= company["demo_end"]
    return True


def tenant_connection(root):
    cid = COMPANY_ID.get()
    get_company(root, cid)
    if is_postgresql():
        from portal_postgres import connect, connect_pooled
        with control(root) as registry:
            row = registry.execute('SELECT secret FROM portal_company_keys WHERE company_id=?', (cid,)).fetchone()
        if row is None:
            raise PermissionError('Контекст компании не подготовлен')
        if getattr(_CONFIG, 'postgres_pool_size', 0):
            return connect_pooled(_CONFIG.postgres_dsn, cid, row[0], max_size=_CONFIG.postgres_pool_size)
        return connect(_CONFIG.postgres_dsn, cid, row[0])
    conn = connect_file(tenant_path(root, cid))
    try:
        row = conn.execute("SELECT company_id FROM portal_tenant_identity").fetchone()
        if row is None or row[0] != cid:
            raise PermissionError("Хранилище компании недоступно")
        return conn
    except Exception:
        conn.close()
        raise


def audit(conn, actor_id, company_id, event, outcome, **details):
    # Deliberately allow only structural metadata. Never request bodies, URLs,
    # exception text, credentials, headers or arbitrary user-provided strings.
    allowed = {k: v for k, v in details.items() if k in {"method", "route", "status", "fields", "entity_id"}}
    conn.execute("INSERT INTO platform_audit(company_id,actor_id,event,outcome,details,created_at) VALUES(?,?,?,?,?,?)",
                 (company_id, actor_id, event, outcome, json.dumps(allowed, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))


def company_values(body, old=None):
    if set(body) - COMPANY_FIELDS:
        raise ValueError("Неизвестные параметры компании")
    values = {"name": "", "status": "active", "monthly_price": 0, "demo_enabled": 0,
              "demo_start": None, "demo_end": None, "user_limit": 15, "service_status": "active",
              "module_toggles": {}}
    if old:
        values.update({k: old[k] for k in values})
        values["module_toggles"] = decode_module_toggles(values["module_toggles"])
    values.update(body)
    values["module_toggles"] = validate_module_toggles(values["module_toggles"])
    if not isinstance(values["name"], str) or not 1 <= len(values["name"].strip()) <= 200:
        raise ValueError("Название: от 1 до 200 символов")
    values["name"] = values["name"].strip()
    if values["status"] not in ("active", "suspended", "archived") or values["service_status"] not in ("active", "suspended", "expired"):
        raise ValueError("Некорректный статус")
    # Integer minor currency units avoid rounding billing amounts.
    if type(values["monthly_price"]) is not int or not 0 <= values["monthly_price"] <= 10**12:
        raise ValueError("Стоимость задаётся целым количеством копеек")
    limit = values["user_limit"]
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 1000000):
        raise ValueError("Некорректный лимит пользователей")
    if old and old["id"] == 1 and limit is not None:
        raise ValueError("Основная PORTAL не имеет лимита")
    if not (old and old["id"] == 1) and limit is None:
        raise ValueError("Для сторонней компании требуется числовой лимит")
    if type(values["demo_enabled"]) not in (int, bool) or values["demo_enabled"] not in (0, 1):
        raise ValueError("Некорректный demo-режим")
    for key in ("demo_start", "demo_end"):
        if values[key] is not None:
            try:
                dt = datetime.fromisoformat(values[key])
                if dt.tzinfo is not None:
                    raise ValueError()
                values[key] = dt.isoformat(timespec="seconds")
            except (ValueError, TypeError):
                raise ValueError("Demo-даты: YYYY-MM-DDTHH:MM:SS, время сервера")
    if values["demo_enabled"] and (not values["demo_start"] or not values["demo_end"]):
        raise ValueError("Для demo нужны обе даты")
    if values["demo_start"] and values["demo_end"] and values["demo_start"] >= values["demo_end"]:
        raise ValueError("Окончание demo должно быть позже начала")
    return values


def provision(root, company_id, registry=None):
    """Copy schema only, never customer rows, credentials or session data."""
    if is_postgresql():
        if registry is None:
            raise RuntimeError('PostgreSQL company provisioning requires its registry transaction')
        # The company and its initial readiness markers commit atomically.
        registry.execute('SELECT portal_provision_company(?)', (company_id,))
        return
    target = tenant_path(root, company_id)
    target.parent.mkdir(exist_ok=True)
    # Exclusive creation: never overwrite a database left by an interrupted run.
    with target.open("xb"):
        pass
    try:
        with connect_file(root) as source:
            schema = source.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END").fetchall()
        with connect_file(target) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for row in schema:
                if row[1] == "portal_tenant_identity" or row[1].startswith(("portal_tenant_", "production_company_")):
                    continue
                if row[0] not in ("table", "index", "trigger", "view"):
                    continue
                sql = row[2].replace("company_id INTEGER NOT NULL DEFAULT 1 CHECK (company_id = 1)",
                                     f"company_id INTEGER NOT NULL DEFAULT {company_id} CHECK (company_id = {company_id})")
                conn.execute(sql)
            stamp_schema(conn, company_id)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def save_company(root, actor_id, body, company_id=None):
    with control(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone() if company_id else None
        if company_id is not None and old is None:
            raise ValueError("Компания не найдена")
        values = company_values(body, old)
        now = datetime.now().isoformat(timespec="seconds")
        db_values = dict(values, module_toggles=json.dumps(values["module_toggles"], sort_keys=True))
        if old:
            with company_scope(company_id), tenant_connection(root) as data:
                active = data.execute("SELECT COUNT(*) FROM app_users WHERE active=1").fetchone()[0]
            if values["user_limit"] is not None and active > values["user_limit"]:
                raise ValueError("Лимит ниже количества активных пользователей")
            conn.execute("UPDATE companies SET " + ",".join(k + "=?" for k in db_values) + ",updated_at=? WHERE id=?",
                         (*db_values.values(), now, company_id))
        else:
            company_id = conn.execute("INSERT INTO companies(" + ",".join(db_values) + ",created_at,updated_at) VALUES(" + ",".join("?" for _ in db_values) + ",?,?)",
                                      (*db_values.values(), now, now)).lastrowid
            provision(root, company_id, conn) if is_postgresql() else provision(root, company_id)
        audit(conn, actor_id, company_id, "company_updated" if old else "company_created", "success", fields=sorted(body))
        return company_id
