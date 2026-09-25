"""Explicit opt-in migration. Never called by normal server startup."""
from production_repository import Repository, utcnow
from decimal import Decimal, ROUND_HALF_UP

DDL = [
 'CREATE TABLE IF NOT EXISTS portal_production_migrations (company_id BIGINT NOT NULL, version INTEGER NOT NULL, applied_at TEXT NOT NULL, PRIMARY KEY(company_id,version))',
 'CREATE TABLE IF NOT EXISTS portal_production (company_id BIGINT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(company_id,kind,id))',
 'CREATE INDEX IF NOT EXISTS portal_production_lookup ON portal_production(company_id,kind,created_at)',
]

def migrate(conn, company_id, dialect='sqlite'):
    r=Repository(conn,company_id,dialect); r.lock()
    for statement in DDL: r.sql(statement)
    if r.ready():
        migrate_activity(r)
        return
    # Current catalog baseline, not a reconstruction or recalculation of history.
    for operation in r.catalog('operations'):
        rates={key: int((Decimal(str(operation[key]))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if operation.get(key) is not None else None for key in ('employee_rate','client_rate')}
        r.insert('tariffs',dict(operation_id=operation['id'],client_id=operation['client_id'],effective_from=utcnow(),**rates))
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,3,?)',(company_id,utcnow()))
    if dialect=='sqlite':
        # Protect immutable facts even against accidental maintenance SQL.
        for action in ('UPDATE','DELETE'):
            condition="WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers')" if action=='UPDATE' else ''
            r.sql(f"CREATE TRIGGER IF NOT EXISTS production_no_{action.lower()} BEFORE {action} ON portal_production {condition} BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
        r.sql("CREATE TRIGGER IF NOT EXISTS production_no_replace BEFORE INSERT ON portal_production WHEN EXISTS(SELECT 1 FROM portal_production WHERE company_id=NEW.company_id AND kind=NEW.kind AND id=NEW.id) BEGIN SELECT RAISE(ABORT,'production identity already exists'); END")
        # Tenant files remain isolated during the transition to central PostgreSQL.
        for action in ('INSERT','UPDATE'):
            r.sql(f"CREATE TRIGGER IF NOT EXISTS production_company_{action.lower()} BEFORE {action} ON portal_production WHEN NEW.company_id!={company_id} BEGIN SELECT RAISE(ABORT,'company_id mismatch'); END")
    migrate_activity(r)

def migrate_activity(r):
    """Version 4 augments the existing session table; no old session is falsified."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=4',(r.company_id,)).fetchone(): return
    if 'portal_activity_id' not in r.columns('app_sessions'):
        r.sql('ALTER TABLE app_sessions ADD COLUMN portal_activity_id TEXT')
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_update')
        r.sql("CREATE TRIGGER production_no_update BEFORE UPDATE ON portal_production WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,4,?)',(r.company_id,utcnow()))
