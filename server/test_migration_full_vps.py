"""One-shot synthetic migration fixture for an isolated VPS test database.

Opt-in only. Run as the postgres OS user; never point this at an existing DB.
Passwords and the generated test PIN are written only to a mode-0600 file.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import quote

SUFFIX = os.environ.get('PORTAL_SYNTHETIC_SUFFIX','20260926')
if not re.fullmatch(r'[A-Za-z0-9_]{1,24}',SUFFIX):
    raise RuntimeError('Invalid PORTAL_SYNTHETIC_SUFFIX')
ROOT = Path('/tmp/portal-migration-full-' + SUFFIX)
DB = 'portal_test_migration_full_' + SUFFIX
ROLES = {
    'migration': 'portal_migration_full_' + SUFFIX,
    'tenant': 'portal_tenant_full_' + SUFFIX,
    'control': 'portal_control_full_' + SUFFIX,
}
MIGRATIONS = ('postgresql_core_stage4b.sql', 'postgresql_stage3.sql',
              'postgresql_runtime.sql', 'postgresql_rls_context.sql',
              'postgresql_stage5_chat_retention.sql',
              'postgresql_stage6_payroll_settlement.sql',
              'postgresql_stage4c.sql')
TENANT_TABLES = (
    'employees', 'app_users', 'app_sessions', 'portal_clients',
    'portal_client_operations', 'manager_client_assignments', 'materials',
    'material_movements', 'operation_material_norms', 'work_log',
    'payroll_payments', 'payroll_transactions', 'client_invoices',
    'client_payments', 'production_jobs', 'production_job_progress',
    'audit_log', 'portal_production_migrations', 'portal_production',
    'work_material_consumption', 'payroll_employee_identities','payroll_settlement_entries',
    'backup_log', 'client_access', 'client_invites', 'client_invoice_items',
    'client_name_overrides', 'client_permissions', 'employee_access_requests',
    'employee_chat_messages', 'employee_chat_settings', 'employee_invites',
    'expense_requests', 'managers', 'marketplace_news',
    'payroll_closure_batches', 'portal_client_requisites',
    'portal_company_requisites', 'portal_manager_service_rates',
    'production_job_assignments', 'products', 'scheduled_runs',
    'system_settings', 'tariff_versions', 'user_roles',
)
CONTROL_TABLES = ('companies', 'platform_owners', 'platform_sessions', 'platform_audit')
STAMP = '2026-09-26 10:15:30'


def db_url(role, password):
    return ('postgresql://' + quote(role) + ':' + quote(password, safe='') +
            '@127.0.0.1:5432/' + DB)


def create_test_database():
    import psycopg
    from psycopg import sql
    if os.environ.get('PORTAL_SYNTHETIC_SETUP') != '1':
        raise RuntimeError('Explicit synthetic setup flag required')
    if os.geteuid() == 0:
        raise RuntimeError('Run as postgres OS user, not root')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if (ROOT / 'secrets.json').exists():
        raise RuntimeError('Synthetic setup already completed')
    passwords = {kind: secrets.token_urlsafe(36) for kind in ROLES}
    pin = secrets.token_urlsafe(18)
    with psycopg.connect('dbname=postgres user=postgres', autocommit=True) as admin:
        if admin.execute('SELECT 1 FROM pg_database WHERE datname=%s', (DB,)).fetchone():
            raise RuntimeError('Synthetic database already exists')
        for kind, role in ROLES.items():
            if admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                raise RuntimeError('Synthetic role already exists: ' + kind)
        for kind, role in ROLES.items():
            admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}')
                          .format(sql.Identifier(role), sql.Literal(passwords[kind])))
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DB)))
    for filename in MIGRATIONS:
        script = (ROOT / 'migrations' / filename).read_text(encoding='utf-8')
        done = subprocess.run(['psql', '-X', '-v', 'ON_ERROR_STOP=1', '-q', '-d', DB],
                              input=script, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError('Synthetic schema migration failed: ' + filename)
    with psycopg.connect('dbname=' + DB + ' user=postgres', autocommit=True) as admin:
        for role in ROLES.values():
            admin.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}')
                          .format(sql.Identifier(DB), sql.Identifier(role)))
            admin.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        migration, tenant, control = (sql.Identifier(ROLES[name])
                                      for name in ('migration', 'tenant', 'control'))
        admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO {}')
                      .format(migration))
        admin.execute(sql.SQL('GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}')
                      .format(migration))
        for table in TENANT_TABLES:
            admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO {}')
                          .format(sql.Identifier(table), tenant))
        admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}')
                      .format(tenant))
        for table in ('portal_runtime_schema', 'portal_rls_context_schema'):
            admin.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(sql.Identifier(table), tenant))
        for table in CONTROL_TABLES:
            admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO {}')
                          .format(sql.Identifier(table), control))
        admin.execute(sql.SQL('GRANT SELECT ON portal_company_keys TO {}').format(control))
        # The migration LOGIN role is subject to the same protected RLS
        # functions as the tenant role; PUBLIC execution is revoked by DDL.
        for role in (migration, tenant, control):
            admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_bind_company(BIGINT,TEXT) TO {}')
                          .format(role))
            admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_current_company() TO {}')
                          .format(role))
        admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_provision_company(BIGINT) TO {}')
                      .format(control))
        for table in ('companies', 'platform_owners', 'platform_audit'):
            sequence = admin.execute('SELECT pg_get_serial_sequence(%s,%s)',
                                     ('public.' + table, 'id')).fetchone()[0]
            if sequence:
                admin.execute(sql.SQL('GRANT USAGE,SELECT ON SEQUENCE {} TO {}')
                              .format(sql.Identifier(*sequence.split('.')), control))
    with psycopg.connect('dbname=' + DB + ' user=postgres') as admin:
        build_copies(admin, pin)
    secrets_file = ROOT / 'secrets.json'
    payload = {kind + '_dsn': db_url(ROLES[kind], passwords[kind]) for kind in ROLES}
    payload['synthetic_pin'] = pin
    fd = os.open(secrets_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(payload, output)
    print('Synthetic DB, three restricted roles, current migrations and three SQLite copies ready')


def schema(conn, table):
    rows = conn.execute('''SELECT column_name,data_type FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position''',
                        (table,)).fetchall()
    if not rows:
        raise RuntimeError('Missing synthetic target table: ' + table)
    return rows


def create_sqlite_table(sqlite, pg, table):
    fields = schema(pg, table)
    types = {'bigint': 'INTEGER', 'integer': 'INTEGER', 'smallint': 'INTEGER',
             'numeric': 'REAL', 'double precision': 'REAL', 'boolean': 'INTEGER'}
    sqlite.execute('CREATE TABLE "' + table + '" (' + ','.join(
        '"' + name + '" ' + types.get(kind, 'TEXT') for name, kind in fields) + ')')
    return [name for name, _ in fields]


def insert(sqlite, table, fields, values):
    sqlite.execute('INSERT INTO "' + table + '" (' +
                   ','.join('"' + name + '"' for name in fields) + ') VALUES (' +
                   ','.join('?' for _ in fields) + ')', tuple(values[name] for name in fields))


def row(columns, **values):
    return {field: values.get(field) for field in columns}


def pin_fields(pin):
    salt = secrets.token_bytes(16)
    return (base64.b64encode(salt).decode(),
            base64.b64encode(hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, 180000)).decode())


def build_copies(pg, pin):
    control_path = ROOT / 'platform-synthetic.db'
    with sqlite3.connect(control_path) as source:
        fields = {table: create_sqlite_table(source, pg, table) for table in CONTROL_TABLES}
        for cid in (1, 2):
            insert(source, 'companies', fields['companies'], row(fields['companies'],
                id=cid, name='PORTAL' if cid == 1 else 'Компания Б — тест',
                status='active', monthly_price=0, demo_enabled=0,
                user_limit=None if cid == 1 else 15, service_status='active',
                created_at=STAMP, updated_at=STAMP))
        salt, digest = pin_fields(pin)
        insert(source, 'platform_owners', fields['platform_owners'], row(fields['platform_owners'],
            id=1, company_id=1, username='synthetic_owner', display_name='Тестовый владелец',
            pin_salt=salt, pin_hash=digest, active=1))
        insert(source, 'platform_audit', fields['platform_audit'], row(fields['platform_audit'],
            id=1, company_id=1, actor_id=1, event='synthetic_setup', outcome='success',
            details='{}', created_at=STAMP))
    os.chmod(control_path, 0o600)
    for cid in (1, 2):
        path = ROOT / ('tenant-%d-synthetic.db' % cid)
        with sqlite3.connect(path) as source:
            fields = {table: create_sqlite_table(source, pg, table) for table in TENANT_TABLES}
            populate_tenant(source, fields, cid, pin)
        os.chmod(path, 0o600)


def populate_tenant(db, columns, cid, pin):
    code = 'A' if cid == 1 else 'B'
    name = 'Клиент «Север»' if cid == 1 else 'Клиент «Юг»'
    product = 'Товар 🧵 ' + code
    employee = 1000 + cid
    def add(table, **values):
        insert(db, table, columns[table], row(columns[table], company_id=cid, **values))
    add('employees', telegram_id=employee, full_name='Сотрудник ' + code,
        username='worker_' + code.lower())
    for uid, role in ((1, 'admin'), (2, 'packer')):
        salt, digest = pin_fields(pin)
        add('app_users', id=uid, username=role + '_' + code.lower(),
            display_name='Сотрудник ' + code + ' ' + role, role=role,
            telegram_id=employee if role == 'packer' else None, active=1,
            pin_salt=salt, pin_hash=digest, created_at=STAMP, updated_at=STAMP)
    add('portal_clients', id=1, name=name, active=1, created_at=STAMP, updated_at=STAMP)
    add('portal_client_operations', id=1, client_id=1, name='Упаковка',
        employee_rate=2.35, client_rate=5.75, active=1, sort_order=1,
        created_at=STAMP, updated_at=STAMP)
    add('manager_client_assignments', telegram_id=employee, client_id=1, active=1)
    add('materials', id=1, name='Плёнка', unit='м', unit_cost=0.75,
        stock_qty=10.5, active=1, min_stock=2, updated_at=STAMP)
    add('material_movements', id=1, material_id=1, qty_change=10.5,
        unit_cost=0.75, movement_type='receipt', reference_type='synthetic',
        reference_id='test', note='Приход', created_at=STAMP, created_by=1)
    add('operation_material_norms', id=1, operation_id=1, material_id=1,
        qty_per_unit=0.5, active=1)
    add('work_log', id=1, telegram_id=employee, username='worker_' + code.lower(),
        first_name='Сотрудник ' + code, client=name, operation='Упаковка',
        quantity=3, rate=2.35, salary=7.05, client_rate=5.75,
        revenue=17.25, direct_cost=1.5, unit_direct_cost=0, anomaly_flag=0,
        created_at=STAMP, updated_at=STAMP)
    add('payroll_payments', id=1, telegram_id=employee, period_start='2026-09-01',
        period_end='2026-09-30', status='partial')
    add('payroll_transactions', id=1, telegram_id=employee, period_start='2026-09-01',
        period_end='2026-09-30', amount=7.05)
    add('client_invoices', id=1, client=name, description='Упаковка',
        amount_due=17.25, due_date='2026-10-01', created_at=STAMP)
    add('client_payments', id=1, invoice_id=1, amount=5.75)
    add('production_jobs', id=1, client=name, operation='Упаковка',
        product_name=product, status='in_progress', target_quantity=10,
        priority=1, due_at='2026-10-01 12:00:00', updated_at=STAMP,
        internal_cost=7.05)
    add('production_job_progress', id=1, job_id=1, work_id=1, telegram_id=employee,
        quantity=3, created_at=STAMP)
    add('audit_log', id=1, actor_id=1, action='synthetic', entity_type='work',
        entity_id='1', details='{}', created_at=STAMP)
    add('work_material_consumption', work_id=1, material_id=1,
        quantity=1.5, unit_cost=0.75, updated_at=STAMP)
    for version in (3, 4, 5):
        add('portal_production_migrations', version=version, applied_at=STAMP)
    ledger = (
        ('batches', 'batch-' + code, {'number': 'PRT-2026-SYNTH-' + code,
                                      'client_id': 1, 'product': product, 'quantity': 10}),
        ('tasks', 'task-' + code, {'batch_id': 'batch-' + code, 'client_id': 1,
                                   'operation_id': 1, 'quantity': 10}),
        ('tariffs', 'old-' + code, {'operation_id': 1, 'client_id': 1,
                                    'employee_rate': 235, 'client_rate': 575,
                                    'effective_from': '2026-09-01'}),
        ('tariffs', 'new-' + code, {'operation_id': 1, 'client_id': 1,
                                    'employee_rate': 250, 'client_rate': 600,
                                    'effective_from': '2026-09-25'}),
        ('works', 'work-' + code, {'task_id': 'task-' + code, 'batch_id': 'batch-' + code,
                                   'salary': 705, 'revenue': 1725, 'quantity': 3}),
        ('plans', 'plan-' + code, {'batch_id': 'batch-' + code,
                                   'task_id': 'task-' + code, 'salary': 705,
                                   'revenue': 1725, 'materials': 150, 'other': 0}),
        ('invoices', 'invoice-' + code, {'work_ids': ['work-' + code], 'amount': 1725}),
        ('payments', 'payment-' + code, {'invoice_id': 'invoice-' + code, 'amount': 575}),
        ('permissions', 'permission-' + code, {'overrides': {'work.write': True}}),
        ('access_events', 'login-' + code, {'result': 'success', 'client_type': 'Android'}),
        ('work_timers', 'timer-' + code, {'task_id': 'task-' + code,
                                         'batch_id': 'batch-' + code, 'net_seconds': 1800}),
        ('usage', 'usage-' + code, {'work_id': 'work-' + code, 'cost': 150}),
        ('expenses', 'expense-' + code, {'amount': 30}),
    )
    for kind, identity, payload in ledger:
        payload.update(id=identity, company_id=cid)
        add('portal_production', kind=kind, id=identity,
            payload=json.dumps(payload, ensure_ascii=False), created_at=STAMP)


if __name__ == '__main__':
    create_test_database()
