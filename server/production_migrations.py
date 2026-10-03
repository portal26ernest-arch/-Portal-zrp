"""Explicit opt-in migration. Never called by normal server startup."""
from production_repository import Repository, utcnow
from client_names import persist_known_client_aliases
from employee_names import persist_known_employee_aliases
from decimal import Decimal, ROUND_HALF_UP

DDL = [
 'CREATE TABLE IF NOT EXISTS portal_production_migrations (company_id BIGINT NOT NULL, version INTEGER NOT NULL, applied_at TEXT NOT NULL, PRIMARY KEY(company_id,version))',
 'CREATE TABLE IF NOT EXISTS portal_production (company_id BIGINT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(company_id,kind,id))',
 'CREATE INDEX IF NOT EXISTS portal_production_lookup ON portal_production(company_id,kind,created_at)',
]

def migrate(conn, company_id, dialect=None):
    dialect = dialect or getattr(conn, 'dialect', 'sqlite')
    r=Repository(conn,company_id,dialect); r.lock()
    if dialect == 'sqlite':
        for statement in DDL: r.sql(statement)
    elif not r.has_table('portal_production_migrations') or not r.has_table('portal_production'):
        raise RuntimeError('Apply PostgreSQL schema migrations with the migration operator first')
    if r.ready():
        migrate_activity(r)
        migrate_retention(r)
        migrate_payroll_settlement(r)
        migrate_invoice_revisions(r)
        migrate_access_invites(r)
        migrate_products(r)
        migrate_client_aliases(r)
        migrate_employee_aliases(r)
        migrate_organizer_requests(r)
        migrate_session_storage(r)
        return
    # Current catalog baseline, not a reconstruction or recalculation of history.
    for operation in r.catalog('operations'):
        rates={key: int((Decimal(str(operation[key]))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if operation.get(key) is not None else None for key in ('employee_rate','client_rate')}
        r.insert('tariffs',dict(operation_id=operation['id'],client_id=operation['client_id'],effective_from=utcnow(),**rates))
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,3,?)',(company_id,utcnow()))
    if dialect=='sqlite':
        # Protect immutable facts even against accidental maintenance SQL.
        for action in ('UPDATE','DELETE'):
            condition="WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers')" if action=='UPDATE' else "WHEN OLD.kind NOT IN ('chat_messages','chat_pins','chat_attachments')"
            r.sql(f"CREATE TRIGGER IF NOT EXISTS production_no_{action.lower()} BEFORE {action} ON portal_production {condition} BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
        r.sql("CREATE TRIGGER IF NOT EXISTS production_no_replace BEFORE INSERT ON portal_production WHEN EXISTS(SELECT 1 FROM portal_production WHERE company_id=NEW.company_id AND kind=NEW.kind AND id=NEW.id) BEGIN SELECT RAISE(ABORT,'production identity already exists'); END")
        # Tenant files remain isolated during the transition to central PostgreSQL.
        for action in ('INSERT','UPDATE'):
            r.sql(f"CREATE TRIGGER IF NOT EXISTS production_company_{action.lower()} BEFORE {action} ON portal_production WHEN NEW.company_id!={company_id} BEGIN SELECT RAISE(ABORT,'company_id mismatch'); END")
    migrate_activity(r)
    migrate_retention(r)
    migrate_payroll_settlement(r)
    migrate_invoice_revisions(r)
    migrate_access_invites(r)
    migrate_client_aliases(r)
    migrate_employee_aliases(r)
    migrate_organizer_requests(r)
    migrate_session_storage(r)

def migrate_session_storage(r):
    from session_security import migrate_tokens
    migrate_tokens(r.conn,r.company_id)
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=15',(r.company_id,)).fetchone():return
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,15,?)',(r.company_id,utcnow()))

def migrate_organizer_requests(r):
    """Version 14 permits request-card mutation; event and attachment rows stay immutable."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=14',(r.company_id,)).fetchone(): return
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_update')
        r.sql("CREATE TRIGGER production_no_update BEFORE UPDATE ON portal_production WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers','products','organizer_tasks','organizer_requests') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
    else:
        row=r.sql("SELECT pg_get_functiondef('portal_production_immutable()'::regprocedure)").fetchone()
        if not row or "'organizer_requests'" not in row[0] or "'organizer_request_events'" in row[0]: raise RuntimeError('Apply PostgreSQL organizer requests migration with the migration operator first')
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,14,?)',(r.company_id,utcnow()))

def migrate_access_invites(r):
    """Version 10 adds the hashed-token invitation table; login secrets are never stored here."""
    if r.dialect=='sqlite':
        r.sql(f'''CREATE TABLE IF NOT EXISTS portal_access_invites (
            company_id INTEGER NOT NULL DEFAULT {r.company_id} CHECK(company_id={r.company_id}),
            id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128),
            token_hash TEXT NOT NULL CHECK(length(token_hash)=64),
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','accepted','approved','revoked','expired','rejected')),
            role TEXT NOT NULL CHECK(role IN ('admin','director','manager','packer','shift','accountant')),
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            employee_id INTEGER,
            request_id TEXT NOT NULL,
            user_id INTEGER,
            accepted_at TEXT,
            decided_at TEXT,
            decided_by INTEGER,
            PRIMARY KEY(company_id,id), UNIQUE(company_id,token_hash), UNIQUE(company_id,request_id)
        )''')
        r.sql('CREATE INDEX IF NOT EXISTS portal_access_invites_status ON portal_access_invites(company_id,status,created_at)')
        r.sql('''CREATE TRIGGER IF NOT EXISTS portal_access_invites_no_delete BEFORE DELETE ON portal_access_invites
                 BEGIN SELECT RAISE(ABORT,'История приглашений неизменяема'); END''')
        r.sql('''CREATE TRIGGER IF NOT EXISTS portal_access_invites_guard_update BEFORE UPDATE ON portal_access_invites
                 WHEN NEW.company_id!=OLD.company_id OR NEW.id!=OLD.id OR NEW.token_hash!=OLD.token_hash
                   OR NEW.created_by!=OLD.created_by OR NEW.created_at!=OLD.created_at OR NEW.expires_at!=OLD.expires_at
                   OR NEW.role!=OLD.role OR NEW.username!=OLD.username OR NEW.display_name!=OLD.display_name
                   OR NEW.employee_id IS NOT OLD.employee_id OR NEW.request_id!=OLD.request_id
                   OR NOT ((OLD.status='pending' AND NEW.status IN ('accepted','revoked','expired'))
                       OR (OLD.status='accepted' AND NEW.status IN ('approved','rejected','revoked')))
                 BEGIN SELECT RAISE(ABORT,'Недопустимое изменение приглашения'); END''')
    elif not r.has_table('portal_access_invites'):
        raise RuntimeError('Примените PostgreSQL-миграцию приглашений оператором')
    if not r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=10',(r.company_id,)).fetchone():
        r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,10,?)',(r.company_id,utcnow()))
    migrate_products(r)

def migrate_products(r):
    """Version 11 permits edits to catalog metadata while preserving snapshots in facts."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=11',(r.company_id,)).fetchone():
        migrate_organizer(r);return
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_update')
        r.sql("CREATE TRIGGER production_no_update BEFORE UPDATE ON portal_production WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers','products') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
    else:
        row=r.sql("SELECT pg_get_functiondef('portal_production_immutable()'::regprocedure)").fetchone()
        if not row or "'products'" not in row[0]:
            raise RuntimeError('Apply PostgreSQL product catalog migration with the migration operator first')
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,11,?)',(r.company_id,utcnow()))
    migrate_organizer(r)

def migrate_organizer(r):
    """Version 12 allows organizer task state edits while keeping organizer history immutable."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=12',(r.company_id,)).fetchone(): return
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_update')
        r.sql("CREATE TRIGGER production_no_update BEFORE UPDATE ON portal_production WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers','products','organizer_tasks') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
    else:
        row=r.sql("SELECT pg_get_functiondef('portal_production_immutable()'::regprocedure)").fetchone()
        if not row or "'organizer_tasks'" not in row[0]:
            raise RuntimeError('Apply PostgreSQL organizer migration with the migration operator first')
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,12,?)',(r.company_id,utcnow()))

def migrate_client_aliases(r):
    """Version 12 backfills approved search aliases without rewriting canonical client names."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=12',(r.company_id,)).fetchone(): return
    for client in r.catalog('clients'):
        persist_known_client_aliases(r,client['id'],client['name'])
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,12,?)',(r.company_id,utcnow()))

def migrate_employee_aliases(r):
    """Version 13 backfills approved employee spelling aliases by stable employee_id."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=13',(r.company_id,)).fetchone(): return
    for employee in r.employee_catalog():
        persist_known_employee_aliases(r,employee['employee_id'],employee['full_name'])
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,13,?)',(r.company_id,utcnow()))


def migrate_activity(r):
    """Version 4 augments the existing session table; no old session is falsified."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=4',(r.company_id,)).fetchone(): return
    if 'portal_activity_id' not in r.columns('app_sessions'):
        r.sql('ALTER TABLE app_sessions ADD COLUMN portal_activity_id TEXT')
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_update')
        r.sql("CREATE TRIGGER production_no_update BEFORE UPDATE ON portal_production WHEN OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,4,?)',(r.company_id,utcnow()))

def migrate_retention(r):
    """Version 5 allows physical deletion only for expiring chat history."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=5',(r.company_id,)).fetchone(): return
    if r.dialect=='sqlite':
        r.sql('DROP TRIGGER IF EXISTS production_no_delete')
        r.sql("CREATE TRIGGER production_no_delete BEFORE DELETE ON portal_production WHEN OLD.kind NOT IN ('chat_messages','chat_pins','chat_attachments') BEGIN SELECT RAISE(ABORT,'production history is immutable'); END")
        r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,5,?)',(r.company_id,utcnow()))
        return
    row=r.sql("SELECT pg_get_functiondef('portal_production_immutable()'::regprocedure)").fetchone()
    definition=row[0] if row else ''
    required=('chat_messages','chat_pins','chat_attachments','production history is immutable')
    if not all(marker in definition for marker in required):
        raise RuntimeError('Apply PostgreSQL chat retention migration with the migration operator first')
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,5,?)',(r.company_id,utcnow()))

def migrate_payroll_settlement(r):
    """Version 6 adds the immutable, integer-minor-unit payroll settlement ledger."""
    if r.dialect=='sqlite':
        r.sql('CREATE UNIQUE INDEX IF NOT EXISTS payroll_employee_legacy_scope ON employees(company_id,telegram_id)')
        r.sql(f'''CREATE TABLE IF NOT EXISTS payroll_employee_identities (
            employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL DEFAULT {r.company_id} CHECK (company_id = {r.company_id}),
            legacy_employee_id INTEGER NOT NULL,
            UNIQUE(company_id,employee_id),
            UNIQUE(company_id,legacy_employee_id),
            FOREIGN KEY(company_id,legacy_employee_id) REFERENCES employees(company_id,telegram_id)
        )''')
        r.sql('''CREATE TABLE IF NOT EXISTS payroll_settlement_entries (
            id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128),
            company_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL CHECK(typeof(employee_id)='integer' AND employee_id>0),
            payroll_period_id TEXT NOT NULL,
            payroll_period_kind TEXT NOT NULL DEFAULT 'payroll_periods' CHECK(payroll_period_kind='payroll_periods'),
            amount_minor INTEGER NOT NULL CHECK(typeof(amount_minor)='integer' AND amount_minor!=0 AND abs(amount_minor)<=100000000000),
            entry_type TEXT NOT NULL CHECK(entry_type IN ('payout','adjustment','reversal')),
            effect TEXT NOT NULL CHECK(effect IN ('payment','entitlement')),
            actor_id INTEGER NOT NULL CHECK(typeof(actor_id)='integer' AND actor_id>0),
            actor_kind TEXT NOT NULL CHECK(actor_kind IN ('user','platform_owner')),
            occurred_at TEXT NOT NULL CHECK(length(occurred_at)>0),
            reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 1000),
            reference TEXT CHECK(reference IS NULL OR length(reference)<=1000),
            request_id TEXT NOT NULL CHECK(length(request_id) BETWEEN 1 AND 128 AND request_id=trim(request_id)),
            reversal_of TEXT,
            PRIMARY KEY(company_id,id),
            UNIQUE(company_id,request_id),
            FOREIGN KEY(company_id,employee_id) REFERENCES payroll_employee_identities(company_id,employee_id),
            FOREIGN KEY(company_id,payroll_period_kind,payroll_period_id) REFERENCES portal_production(company_id,kind,id),
            FOREIGN KEY(company_id,reversal_of) REFERENCES payroll_settlement_entries(company_id,id),
            CHECK((entry_type='payout' AND effect='payment' AND amount_minor>0 AND reversal_of IS NULL)
               OR (entry_type='adjustment' AND effect='entitlement' AND reversal_of IS NULL)
               OR (entry_type='reversal' AND reversal_of IS NOT NULL))
        )''')
        r.sql('CREATE INDEX IF NOT EXISTS payroll_settlement_period_employee ON payroll_settlement_entries(company_id,payroll_period_id,employee_id,occurred_at)')
        r.sql('CREATE INDEX IF NOT EXISTS payroll_settlement_employee ON payroll_settlement_entries(company_id,employee_id,occurred_at)')
        r.sql('CREATE UNIQUE INDEX IF NOT EXISTS payroll_settlement_one_reversal ON payroll_settlement_entries(company_id,reversal_of) WHERE reversal_of IS NOT NULL')
        for action in ('UPDATE','DELETE'):
            r.sql(f"CREATE TRIGGER IF NOT EXISTS payroll_settlement_no_{action.lower()} BEFORE {action} ON payroll_settlement_entries BEGIN SELECT RAISE(ABORT,'История расчётов зарплаты неизменяема'); END")
            r.sql(f"CREATE TRIGGER IF NOT EXISTS payroll_identity_no_{action.lower()} BEFORE {action} ON payroll_employee_identities BEGIN SELECT RAISE(ABORT,'Связь сотрудника расчёта неизменяема'); END")
        r.sql('''CREATE TRIGGER IF NOT EXISTS payroll_settlement_company_insert BEFORE INSERT ON payroll_settlement_entries
                 WHEN NEW.company_id IS NULL OR NEW.company_id!=(SELECT company_id FROM portal_tenant_identity)
                 BEGIN SELECT RAISE(ABORT,'Компания записи не совпадает'); END''')
        r.sql('''CREATE TRIGGER IF NOT EXISTS payroll_settlement_closed_period BEFORE INSERT ON payroll_settlement_entries
                 WHEN NOT EXISTS (
                    SELECT 1 FROM portal_production p
                    JOIN payroll_employee_identities i ON i.company_id=p.company_id AND i.employee_id=NEW.employee_id
                    WHERE p.company_id=NEW.company_id AND p.kind='payroll_periods' AND p.id=NEW.payroll_period_id
                      AND json_extract(p.payload,'$.status')='closed'
                      AND EXISTS (SELECT 1 FROM json_each(p.payload,'$.snapshot.employees') s
                                  WHERE json_extract(s.value,'$.employee_id')=i.legacy_employee_id))
                 BEGIN SELECT RAISE(ABORT,'Сотрудник отсутствует в закрытом расчётном периоде'); END''')
        r.sql('''CREATE TRIGGER IF NOT EXISTS payroll_settlement_reversal_matches BEFORE INSERT ON payroll_settlement_entries
                 WHEN NEW.entry_type='reversal' AND NOT EXISTS (
                    SELECT 1 FROM payroll_settlement_entries e WHERE e.company_id=NEW.company_id AND e.id=NEW.reversal_of
                      AND e.entry_type IN ('payout','adjustment') AND e.employee_id=NEW.employee_id
                      AND e.payroll_period_id=NEW.payroll_period_id AND e.effect=NEW.effect AND e.amount_minor=-NEW.amount_minor)
                 BEGIN SELECT RAISE(ABORT,'Сторно должно точно компенсировать исходную запись'); END''')
        r.sql('''CREATE TRIGGER IF NOT EXISTS payroll_settlement_payout_balance BEFORE INSERT ON payroll_settlement_entries
                 WHEN NEW.entry_type='payout' AND NEW.amount_minor>(
                    SELECT coalesce(sum(json_extract(s.value,'$.salary')),0) FROM portal_production p
                    JOIN payroll_employee_identities i ON i.company_id=p.company_id AND i.employee_id=NEW.employee_id
                    JOIN json_each(p.payload,'$.snapshot.employees') s
                    WHERE p.company_id=NEW.company_id AND p.kind='payroll_periods' AND p.id=NEW.payroll_period_id
                      AND json_extract(s.value,'$.employee_id')=i.legacy_employee_id
                 )+(
                    SELECT coalesce(sum(CASE WHEN effect='entitlement' THEN amount_minor ELSE -amount_minor END),0)
                    FROM payroll_settlement_entries WHERE company_id=NEW.company_id
                      AND payroll_period_id=NEW.payroll_period_id AND employee_id=NEW.employee_id)
                 BEGIN SELECT RAISE(ABORT,'Сумма выплаты превышает остаток по закрытому периоду'); END''')
    elif not r.has_table('payroll_settlement_entries') or not r.has_table('payroll_employee_identities'):
        raise RuntimeError('Примените PostgreSQL-миграцию реестра расчётов зарплаты оператором')
    validate_payroll_settlement(r)
    r.sync_payroll_employees()
    if not r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=6',(r.company_id,)).fetchone():
        r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,6,?)',(r.company_id,utcnow()))
    from documents_schema import migrate_documents
    migrate_documents(r)

def migrate_invoice_revisions(r):
    """Version 9 marks readiness for the append-only invoice revision workflow."""
    if r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=9',(r.company_id,)).fetchone():return
    r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,9,?)',(r.company_id,utcnow()))


def validate_payroll_settlement(r):
    """Fail closed on an older draft or missing append-only/insert protections."""
    if not {'actor_kind','payroll_period_kind','amount_minor','employee_id','request_id'}.issubset(r.columns('payroll_settlement_entries')):
        raise RuntimeError('Схема расчётов зарплаты требует проверки оператором')
    if r.dialect=='sqlite':
        required={'payroll_settlement_no_update','payroll_settlement_no_delete',
                  'payroll_settlement_closed_period','payroll_settlement_reversal_matches',
                  'payroll_identity_no_update','payroll_identity_no_delete','payroll_settlement_company_insert',
                  'payroll_settlement_payout_balance'}
        names={row[0] for row in r.sql("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
    else:
        required={'payroll_settlement_immutable','payroll_settlement_valid','payroll_identity_immutable'}
        names={row[0] for row in r.sql("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='O' AND tgrelid IN ('payroll_settlement_entries'::regclass,'payroll_employee_identities'::regclass)").fetchall()}
        definitions=r.sql("SELECT pg_get_functiondef('portal_payroll_settlement_validate()'::regprocedure),pg_get_functiondef('portal_payroll_settlement_immutable()'::regprocedure)").fetchone()
        if not all(part in definitions[0] for part in ('payroll_periods','closed','reversal_of','legacy_employee_id')) or 'RAISE EXCEPTION' not in definitions[1]:
            raise RuntimeError('Защита расчётов зарплаты требует проверки оператором')
    if not required.issubset(names):
        raise RuntimeError('Защита истории расчётов зарплаты неполна')
