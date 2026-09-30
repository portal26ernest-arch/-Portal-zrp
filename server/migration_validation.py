"""Read-only reconciliation of a SQLite copy and a future PostgreSQL import.

This module does not connect to a deployment or perform the import. Callers supply
two DB-API connections and must abort cutover when ``compare`` raises.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


TABLES = (
    'portal_production', 'portal_production_migrations',
    'employees', 'app_users', 'app_sessions', 'portal_clients', 'portal_client_operations',
    'work_log', 'payroll_payments', 'payroll_transactions',
    'client_invoices', 'client_payments', 'materials', 'material_movements',
    'operation_material_norms', 'manager_client_assignments', 'audit_log',
    'production_jobs', 'production_job_progress', 'work_material_consumption',
)
REQUIRED = {'employees', 'portal_clients', 'portal_client_operations', 'work_log'}


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
    if type(value) in (int, float, Decimal):
        return str(Decimal(str(value)).normalize())
    return value


def snapshot(conn, dialect, company_id, projection=None):
    """Hash company-scoped rows without printing credentials or personal data."""
    if type(company_id) is not int or company_id < 1:
        raise ValidationError('Invalid company_id')
    result = {}
    for table in TABLES:
        columns = _columns(conn, dialect, table)
        if projection is not None and table not in projection:
            if columns and conn.execute('SELECT 1 FROM ' + table +
                                        ' WHERE company_id=%s LIMIT 1',
                                        (company_id,)).fetchone():
                raise ValidationError('Unexpected target rows: ' + table)
            continue
        if not columns:
            if table in REQUIRED:
                raise ValidationError('Missing required table: ' + table)
            continue
        if 'company_id' not in columns:
            raise ValidationError('Missing company_id: ' + table)
        # Older SQLite copies may lack columns newly added to PostgreSQL. Hash
        # every source column in the destination and reject missing columns.
        fields = sorted(projection[table]['columns'] if projection is not None else columns)
        if not set(fields).issubset(columns):
            raise ValidationError('Missing target columns: ' + table)
        placeholder = '%s' if dialect == 'postgresql' else '?'
        cursor = conn.execute('SELECT ' + ','.join(fields) + ' FROM ' + table +
                              ' WHERE company_id=' + placeholder, (company_id,))
        hashes = []
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                if row[fields.index('company_id')] != company_id:
                    raise ValidationError('Company scope mismatch: ' + table)
                record = dict(zip(fields, (_normalize(value) for value in row)))
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


def reconcile_linked_work_money(legacy_conn, ledger_conn, company_id,
                                legacy_dialect='sqlite', ledger_dialect='sqlite',
                                canonical_work_ids=None):
    """Read-only exact reconciliation for legacy work rows linked from the ledger.

    Legacy work facts store currency in major units while canonical ledger payloads
    store integer minor units. Only rows explicitly linked by ``legacy_id`` are
    compared; both reads are company-scoped and this function never writes. An
    optional canonical work ID set supports a bounded per-record check; omitting
    it performs the complete company scan and detects duplicate legacy links.
    """
    if type(company_id) is not int or company_id < 1:
        raise ValidationError('Invalid company_id')
    selected_work_ids = None
    if canonical_work_ids is not None:
        if isinstance(canonical_work_ids, (str, bytes)):
            raise ValidationError('Invalid canonical work filter')
        try:
            selected_work_ids = {str(identity) for identity in canonical_work_ids}
        except TypeError as exc:
            raise ValidationError('Invalid canonical work filter') from exc
        if not selected_work_ids or any(not identity for identity in selected_work_ids):
            raise ValidationError('Invalid canonical work filter')
    legacy_columns = _columns(legacy_conn, legacy_dialect, 'work_log')
    if not {'id', 'company_id'}.issubset(legacy_columns):
        raise ValidationError('Missing legacy work identity columns')
    fields = [field for field in ('rate', 'salary', 'client_rate', 'revenue', 'direct_cost')
              if field in legacy_columns]
    if not fields:
        raise ValidationError('Missing legacy work money columns')
    legacy_placeholder = '%s' if legacy_dialect == 'postgresql' else '?'
    legacy_sql = ('SELECT id,' + ','.join(fields) + ' FROM work_log WHERE company_id=' +
                  legacy_placeholder)
    legacy_rows = legacy_conn.execute(legacy_sql, (company_id,)).fetchall()
    legacy_by_id = {}
    for row in legacy_rows:
        identity = int(row[0])
        if identity in legacy_by_id:
            raise ValidationError('Duplicate company-scoped legacy work identity')
        legacy_by_id[identity] = dict(zip(fields, row[1:]))

    ledger_placeholder = '%s' if ledger_dialect == 'postgresql' else '?'
    ledger_sql = ('SELECT payload FROM portal_production WHERE company_id=' +
                  ledger_placeholder + " AND kind='works'")
    canonical_rows = ledger_conn.execute(ledger_sql, (company_id,)).fetchall()
    usage_sql = ('SELECT payload FROM portal_production WHERE company_id=' +
                 ledger_placeholder + " AND kind='usage'")
    usage_rows = ledger_conn.execute(usage_sql, (company_id,)).fetchall()
    usage_by_work = {}
    for row in usage_rows:
        try:
            usage = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise ValidationError('Invalid canonical usage payload') from exc
        if usage.get('company_id') != company_id:
            raise ValidationError('Canonical usage company mismatch')
        work_id = usage.get('work_id')
        if selected_work_ids is not None and str(work_id) not in selected_work_ids:
            continue
        cost = usage.get('cost')
        source = usage.get('source')
        if work_id is None or type(cost) is not int or source not in ('norm', 'additional_actual'):
            raise ValidationError('Invalid canonical usage money field')
        # The legacy direct_cost column is the original work-time projection.
        # Later additional_actual entries remain append-only ledger facts and
        # intentionally do not rewrite that legacy snapshot.
        if source != 'norm':
            continue
        key = str(work_id)
        usage_by_work[key] = usage_by_work.get(key, 0) + cost
    legacy_to_canonical = {'rate': 'employee_rate', 'salary': 'salary',
                           'client_rate': 'client_rate', 'revenue': 'revenue',
                           'direct_cost': 'direct_cost'}
    matched = checked = 0
    linked_legacy_ids = set()
    for row in canonical_rows:
        try:
            work = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise ValidationError('Invalid canonical work payload') from exc
        if work.get('company_id') != company_id:
            raise ValidationError('Canonical work company mismatch')
        if selected_work_ids is not None and str(work.get('id')) not in selected_work_ids:
            continue
        if work.get('legacy_id') is None:
            continue
        try:
            legacy_id = int(work['legacy_id'])
        except (TypeError, ValueError) as exc:
            raise ValidationError('Invalid linked legacy work identity') from exc
        if legacy_id in linked_legacy_ids:
            raise ValidationError('Duplicate canonical link to legacy work')
        linked_legacy_ids.add(legacy_id)
        legacy = legacy_by_id.get(legacy_id)
        if legacy is None:
            raise ValidationError('Linked legacy work row is missing')
        matched += 1
        for old_field in fields:
            old_value = legacy[old_field]
            if old_field == 'direct_cost':
                canonical_work_id = work.get('id')
                if canonical_work_id is None:
                    raise ValidationError('Missing canonical work identity for direct_cost')
                new_value = usage_by_work.get(str(canonical_work_id), 0)
                if old_value is None and new_value == 0:
                    continue
            else:
                new_field = legacy_to_canonical[old_field]
                new_value = work.get(new_field)
            if old_value is None and new_value is None:
                continue
            try:
                major = Decimal(str(old_value))
                if not major.is_finite():
                    raise ValidationError('Invalid legacy work money field: ' + old_field)
                if type(new_value) is not int:
                    raise ValidationError('Invalid canonical minor-unit field: ' + old_field)
                expected_minor = int((major * 100).quantize(Decimal('1'),
                                                         rounding=ROUND_HALF_UP))
            except ValidationError:
                raise
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError('Invalid linked work money field: ' + old_field) from exc
            if expected_minor != new_value:
                raise ValidationError('Legacy/canonical work money mismatch: ' + old_field)
            checked += 1
    return {'matched_work_count': matched,
            'unlinked_legacy_work_count': len(legacy_by_id) - len(linked_legacy_ids),
            'money_fields_checked': checked}


def compare_migration_history(source_rows, destination_rows, required_version=6):
    """Preserve source history exactly and allow only the required cutover marker."""
    source = {int(version): applied_at for version, applied_at in source_rows}
    destination = {int(version): applied_at for version, applied_at in destination_rows}
    if len(source) != len(source_rows) or len(destination) != len(destination_rows):
        raise ValidationError('Migration validation failed: portal_production_migrations')
    for version, applied_at in source.items():
        if destination.get(version) != applied_at:
            raise ValidationError('Migration validation failed: portal_production_migrations')
    allowed = set(source)
    allowed.add(required_version)
    if set(destination) != allowed or required_version not in destination or not destination[required_version]:
        raise ValidationError('Migration validation failed: portal_production_migrations')
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
