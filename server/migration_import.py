"""Transactional import from read-only SQLite copies into a prepared PostgreSQL schema.

The importer never creates target tables or edits SQLite. It fails closed when
schema, tenant ownership, row hashes or accounting snapshots differ.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from migration_validation import ValidationError

REQUIRED = {
    'portal_clients': {'id', 'name'},
    'portal_client_operations': {'id', 'client_id', 'name'},
    'work_log': {'id', 'client', 'operation', 'quantity', 'salary'},
    'employees': {'telegram_id'},
}
SKIP = {'portal_tenant_identity'}
IMPORT_ORDER = ('employees', 'app_users', 'app_sessions', 'portal_clients',
                'portal_client_operations', 'manager_client_assignments',
                'materials', 'material_movements', 'operation_material_norms',
                'work_log', 'payroll_payments', 'payroll_transactions',
                'client_invoices', 'client_payments', 'production_jobs',
                'production_job_progress', 'audit_log',
                'portal_production_migrations', 'portal_production')
MONEY = {
    'work_log': ('salary', 'revenue', 'direct_cost'),
    'payroll_transactions': ('amount',),
    'client_invoices': ('amount_due',),
    'client_payments': ('amount',),
}
LEDGER_MONEY = {
    'works': ('salary', 'revenue'), 'plans': ('salary', 'revenue', 'materials', 'other'),
    'invoices': ('amount',), 'payments': ('amount',),
    'usage': ('cost',), 'expenses': ('amount',),
}
KINDS = {'batches', 'tasks', 'works', 'tariffs', 'permissions', 'plans',
         'invoices', 'payments', 'access_events', 'work_timers'}
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def ident(value):
    if not IDENTIFIER.fullmatch(value):
        raise ValidationError('Unsupported SQL identifier')
    return '"' + value + '"'


def open_copy(path):
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValidationError('SQLite backup copy is not a file')
    conn = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        conn.close()
        raise ValidationError('SQLite backup copy failed integrity_check')
    return conn


def source_tables(conn):
    names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        if row[0] not in SKIP]
    return sorted(names, key=lambda name: (IMPORT_ORDER.index(name) if name in IMPORT_ORDER
                                           else len(IMPORT_ORDER), name))


def source_columns(conn, table):
    return [row[1] for row in conn.execute('PRAGMA table_info(' + ident(table) + ')')]


def prepared_source(conn, company_id):
    """Preflight and return source schema. Legacy unscoped rows belong to #1 only."""
    if type(company_id) is not int or company_id < 1:
        raise ValidationError('Invalid company_id')
    tables = source_tables(conn)
    for table, required in REQUIRED.items():
        if table not in tables or not required.issubset(source_columns(conn, table)):
            raise ValidationError('Missing required source schema: ' + table)
    columns = {}
    for table in tables:
        fields = source_columns(conn, table)
        if 'company_id' not in fields and company_id != 1:
            raise ValidationError('Unscoped legacy table outside primary company: ' + table)
        if 'company_id' in fields and conn.execute(
                'SELECT 1 FROM ' + ident(table) + ' WHERE company_id IS NULL OR company_id != ? LIMIT 1',
                (company_id,)).fetchone():
            raise ValidationError('Source contains a different company: ' + table)
        columns[table] = fields + ([] if 'company_id' in fields else ['company_id'])
    # Active catalogue relationships must be sound. Historic work_log retains
    # text names and is deliberately not remapped to today's catalogue.
    if conn.execute('SELECT 1 FROM portal_client_operations o LEFT JOIN portal_clients c '
                    'ON o.client_id=c.id WHERE c.id IS NULL LIMIT 1').fetchone():
        raise ValidationError('Operation/client relationship is broken')
    if {'client_payments', 'client_invoices'}.issubset(tables) and 'invoice_id' in source_columns(conn, 'client_payments'):
        if conn.execute('SELECT 1 FROM client_payments p LEFT JOIN client_invoices i '
                        'ON p.invoice_id=i.id WHERE i.id IS NULL LIMIT 1').fetchone():
            raise ValidationError('Legacy payment/invoice relationship is broken')
    if 'portal_production' in tables:
        seen_numbers = set()
        ids = {}
        for kind, identity, payload in conn.execute(
                'SELECT kind,id,payload FROM portal_production'):
            try:
                data = json.loads(payload)
            except (TypeError, ValueError) as exc:
                raise ValidationError('Invalid production payload') from exc
            if data.get('company_id') != company_id or str(data.get('id')) != identity:
                raise ValidationError('Production identity/company mismatch')
            ids.setdefault(kind, set()).add(identity)
            if kind == 'batches':
                number = data.get('number')
                if not number or number in seen_numbers:
                    raise ValidationError('Duplicate/missing batch number')
                seen_numbers.add(number)
        for kind, identity, payload in conn.execute(
                "SELECT kind,id,payload FROM portal_production"):
            data = json.loads(payload)
            links = [('batch_id', 'batches')] if kind in ('tasks', 'plans', 'links', 'work_timers') else []
            if kind == 'plans': links.append(('task_id', 'tasks'))
            if kind == 'links': links.append(('work_id', 'works'))
            if kind == 'payments': links.append(('invoice_id', 'invoices'))
            if kind == 'works':
                links.extend((('task_id', 'tasks'), ('batch_id', 'batches')))
            if kind == 'work_timers': links.append(('task_id', 'tasks'))
            if kind in ('usage', 'timer_events'):
                links.append(('work_id', 'works') if kind == 'usage' else ('session_id', 'work_timers'))
            for field, target_kind in links:
                if data.get(field) and data[field] not in ids.get(target_kind, set()):
                    raise ValidationError('Broken production relationship: ' + kind)
            if kind == 'invoices' and any(work_id not in ids.get('works', set())
                                          for work_id in data.get('work_ids', [])):
                raise ValidationError('Broken invoice/work relationship')
    return columns


def _canon(value):
    if isinstance(value, bytes): return {'sha256': hashlib.sha256(value).hexdigest()}
    if isinstance(value, (float, Decimal)): return str(Decimal(str(value)).normalize())
    return value


def _digest(rows, fields):
    hashes = []
    for row in rows:
        record = {key: _canon(value) for key, value in zip(fields, row)}
        if 'payload' in record and isinstance(record['payload'], str):
            record['payload'] = json.loads(record['payload'])
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), default=str).encode()
        hashes.append(hashlib.sha256(encoded).digest())
    return len(hashes), hashlib.sha256(b''.join(sorted(hashes))).hexdigest()


def rows_from_source(conn, table, fields, company_id):
    old = source_columns(conn, table)
    cursor = conn.execute('SELECT ' + ','.join(ident(x) for x in old) + ' FROM ' + ident(table))
    for row in cursor:
        yield tuple(row) + (() if 'company_id' in old else (company_id,))


def money_from_rows(rows, fields, table):
    totals = {}
    for row in rows:
        item = dict(zip(fields, row))
        for field in MONEY.get(table, ()):
            if field in item and item[field] is not None:
                key = table + '.' + field
                totals[key] = totals.get(key, Decimal(0)) + Decimal(str(item[field]))
        if table == 'portal_production':
            payload = item['payload'] if isinstance(item['payload'], dict) else json.loads(item['payload'])
            for field in LEDGER_MONEY.get(item['kind'], ()):
                if payload.get(field) is not None:
                    key = 'ledger/' + item['kind'] + '.' + field
                    totals[key] = totals.get(key, Decimal(0)) + Decimal(str(payload[field]))
    return {key: str(value) for key, value in totals.items()}


def summary(conn, columns, company_id):
    counts, totals, digests = {}, {}, {}
    for table, fields in columns.items():
        counts[table], digest = _digest(rows_from_source(conn, table, fields, company_id), fields)
        digests[table] = (counts[table], digest)
        totals.update(money_from_rows(rows_from_source(conn, table, fields, company_id), fields, table))
    if 'portal_production' in columns:
        for kind in KINDS:
            count = sum(1 for (row_kind,) in conn.execute(
                'SELECT kind FROM portal_production WHERE kind=?', (kind,)))
            counts['portal_production/' + kind] = count
    return {'counts': counts, 'money': totals, 'digests': digests}


def target_columns(target, table, dialect):
    if dialect == 'sqlite':
        return [r[1] for r in target.execute('PRAGMA table_info(' + ident(table) + ')')]
    return [r[0] for r in target.execute(
        'SELECT column_name FROM information_schema.columns '
        'WHERE table_schema=current_schema() AND table_name=%s', (table,)).fetchall()]


def transfer(source, target, company_id, dialect='postgresql'):
    """Call inside one target transaction. A mismatch raises and rolls it back."""
    columns = prepared_source(source, company_id)
    expected = summary(source, columns, company_id)
    mark = '%s' if dialect == 'postgresql' else '?'
    if dialect == 'postgresql':
        target.execute("SELECT set_config('portal.company_id', %s, true)", (str(company_id),))
    for table, fields in columns.items():
        if not set(fields).issubset(target_columns(target, table, dialect)):
            raise ValidationError('Target schema missing columns: ' + table)
        if target.execute('SELECT 1 FROM ' + ident(table) + ' WHERE company_id=' + mark + ' LIMIT 1',
                          (company_id,)).fetchone():
            raise ValidationError('Target is not empty: ' + table)
        query = ('INSERT INTO ' + ident(table) + '(' + ','.join(ident(f) for f in fields) +
                 ') VALUES (' + ','.join(mark for _ in fields) + ')')
        for row in rows_from_source(source, table, fields, company_id):
            target.execute(query, row)
        result = target.execute('SELECT ' + ','.join(ident(f) for f in fields) +
                                ' FROM ' + ident(table) + ' WHERE company_id=' + mark,
                                (company_id,))
        if _digest(result, fields) != expected['digests'][table]:
            raise ValidationError('Migration FAILED: row mismatch in ' + table)
        target_rows = target.execute('SELECT ' + ','.join(ident(f) for f in fields) +
                                     ' FROM ' + ident(table) + ' WHERE company_id=' + mark,
                                     (company_id,))
        actual_money = money_from_rows(target_rows, fields, table)
        source_money = {key: value for key, value in expected['money'].items()
                        if key.startswith(table + '.') or (table == 'portal_production' and key.startswith('ledger/'))}
        if actual_money != source_money:
            raise ValidationError('Migration FAILED: money mismatch in ' + table)
    return {'company_id': company_id, 'counts': expected['counts'], 'money': expected['money']}


def transfer_control(source, target, dialect='postgresql'):
    """Import the separate platform copy, or seed the pre-platform primary company."""
    mark = '%s' if dialect == 'postgresql' else '?'
    if source is None:
        if not {'id', 'name', 'created_at', 'updated_at'}.issubset(
                target_columns(target, 'companies', dialect)):
            raise ValidationError('Target companies schema is incomplete')
        if target.execute('SELECT 1 FROM companies LIMIT 1').fetchone():
            raise ValidationError('Target companies is not empty')
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
        target.execute('INSERT INTO companies(id,name,created_at,updated_at) VALUES('
                       + ','.join(mark for _ in range(4)) + ')', (1, 'PORTAL', now, now))
        return {'companies': 1, 'legacy_primary_company': True}
    tables = source_tables(source)
    if 'companies' not in tables or not {'id', 'name'}.issubset(source_columns(source, 'companies')):
        raise ValidationError('Platform copy lacks companies')
    order = [name for name in ('companies', 'platform_owners', 'platform_sessions',
                               'platform_audit') if name in tables]
    if set(tables) != set(order):
        raise ValidationError('Unexpected platform table; migration mapping required')
    counts = {}
    for table in order:
        fields = source_columns(source, table)
        if not set(fields).issubset(target_columns(target, table, dialect)):
            raise ValidationError('Target platform schema missing columns: ' + table)
        if target.execute('SELECT 1 FROM ' + ident(table) + ' LIMIT 1').fetchone():
            raise ValidationError('Target platform table is not empty: ' + table)
        selection = 'SELECT ' + ','.join(ident(f) for f in fields) + ' FROM ' + ident(table)
        expected = _digest(source.execute(selection), fields)
        query = ('INSERT INTO ' + ident(table) + '(' + ','.join(ident(f) for f in fields) +
                 ') VALUES (' + ','.join(mark for _ in fields) + ')')
        for row in source.execute(selection):
            if dialect == 'postgresql' and 'company_id' in fields:
                target.execute("SELECT set_config('portal.company_id', %s, true)",
                               (str(row[fields.index('company_id')]),))
            target.execute(query, row)
        if _digest(target.execute(selection), fields) != expected:
            raise ValidationError('Migration FAILED: platform mismatch in ' + table)
        counts[table] = expected[0]
    return counts
