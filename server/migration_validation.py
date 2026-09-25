"""Read-only reconciliation of a SQLite copy and a future PostgreSQL import.

This module does not connect to a deployment or perform the import. Callers supply
two DB-API connections and must abort cutover when ``compare`` raises.
"""

import hashlib
import json
from decimal import Decimal


TABLES = (
    'portal_production', 'portal_production_migrations',
    'app_users', 'app_sessions', 'portal_clients', 'portal_client_operations',
    'work_log', 'payroll_payments', 'payroll_transactions',
    'client_invoices', 'client_payments', 'materials', 'material_movements',
    'operation_material_norms', 'manager_client_assignments', 'audit_log',
)
REQUIRED = {'portal_production', 'portal_production_migrations', 'app_users',
            'portal_clients', 'portal_client_operations', 'work_log'}


class ValidationError(ValueError):
    """The imported data is incomplete, altered, or scoped incorrectly."""


def _columns(conn, dialect, table):
    if table not in TABLES:
        raise ValidationError('Unknown reconciliation table')
    if dialect == 'sqlite':
        return [row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')]
    if dialect == 'postgresql':
        return [row[0] for row in conn.execute(
            'SELECT column_name FROM information_schema.columns '
            'WHERE table_schema=current_schema() AND table_name=%s '
            'ORDER BY ordinal_position', (table,)).fetchall()]
    raise ValidationError('Unsupported database dialect')


def _normalize(value):
    if isinstance(value, bytes):
        return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
    if isinstance(value, (Decimal, float)):
        return str(Decimal(str(value)).normalize())
    return value


def snapshot(conn, dialect, company_id):
    """Hash company-scoped rows without printing credentials or personal data."""
    if type(company_id) is not int or company_id < 1:
        raise ValidationError('Invalid company_id')
    result = {}
    for table in TABLES:
        columns = _columns(conn, dialect, table)
        if not columns:
            if table in REQUIRED:
                raise ValidationError('Missing required table: ' + table)
            continue
        if 'company_id' not in columns:
            raise ValidationError('Missing company_id: ' + table)
        # The source and destination must contain the same columns, including
        # monetary snapshots and tariff versions inside portal_production.
        fields = sorted(columns)
        placeholder = '%s' if dialect == 'postgresql' else '?'
        cursor = conn.execute('SELECT ' + ','.join(fields) + ' FROM ' + table +
                              ' WHERE company_id=' + placeholder, (company_id,))
        hashes = []
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                record = dict(zip(fields, (_normalize(value) for value in row)))
                if record['company_id'] != company_id:
                    raise ValidationError('Company scope mismatch: ' + table)
                if table == 'portal_production':
                    try:
                        payload = (record['payload'] if isinstance(record['payload'], dict)
                                   else json.loads(record['payload']))
                    except (TypeError, ValueError) as exc:
                        raise ValidationError('Invalid ledger payload') from exc
                    if payload.get('company_id') != company_id or str(payload.get('id')) != str(record['id']):
                        raise ValidationError('Ledger identity mismatch')
                    record['payload'] = payload
                encoded = json.dumps(record, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=str).encode('utf-8')
                hashes.append(hashlib.sha256(encoded).digest())
        digest = hashlib.sha256(b''.join(sorted(hashes))).hexdigest()
        result[table] = {'columns': fields, 'count': len(hashes), 'sha256': digest}
    return result


def compare(source, destination):
    """Fail closed on missing tables, schema drift, row count or value drift."""
    for table in TABLES:
        if source.get(table) != destination.get(table):
            raise ValidationError('Migration validation failed: ' + table)
    return True


def validate_postgresql_schema(sql):
    """Static contract check; this is not a PostgreSQL integration test."""
    for table in ('portal_production', 'portal_production_migrations'):
        for clause in (f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY',
                       f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'):
            if clause not in sql:
                raise ValidationError('Missing PostgreSQL RLS contract: ' + table)
    required = ('PRIMARY KEY(company_id, kind, id)',
                "(payload::jsonb ->> 'company_id')::bigint = company_id",
                "payload::jsonb ->> 'id' = id",
                'CREATE UNIQUE INDEX IF NOT EXISTS portal_batch_number_unique',
                'CREATE TRIGGER production_immutable',
                'CREATE POLICY production_company',
                'CREATE POLICY production_migration_company')
    if any(clause not in sql for clause in required):
        raise ValidationError('Incomplete PostgreSQL ledger schema')
    return True
