"""Explicit additive version 7; never run from ordinary server startup."""
from production_repository import utcnow

DOCUMENT_DDL = '''CREATE TABLE IF NOT EXISTS portal_documents (
 company_id BIGINT NOT NULL,
 id TEXT NOT NULL,
 document_type TEXT NOT NULL CHECK(document_type IN ('payroll_xlsx','payroll_slip_xlsx','payroll_slip_pdf','invoice_xlsx','invoice_pdf','report_xlsx','report_pdf','import_template_xlsx','import_result')),
 category TEXT NOT NULL,
 title TEXT NOT NULL,
 original_filename TEXT NOT NULL,
 storage_key TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 size_bytes BIGINT NOT NULL CHECK(size_bytes>0 AND size_bytes<=10485760),
 checksum_sha256 TEXT NOT NULL CHECK(length(checksum_sha256)=64),
 client_id BIGINT,
 employee_id BIGINT,
 invoice_id TEXT,
 invoice_kind TEXT NOT NULL DEFAULT 'invoices' CHECK(invoice_kind='invoices'),
 payroll_period_id TEXT,
 payroll_period_kind TEXT NOT NULL DEFAULT 'payroll_periods' CHECK(payroll_period_kind='payroll_periods'),
 created_by BIGINT NOT NULL CHECK(created_by>0),
 actor_kind TEXT NOT NULL CHECK(actor_kind IN ('user','platform_owner')),
 created_at TEXT NOT NULL,
 document_date TEXT,
 status TEXT NOT NULL CHECK(status IN ('ready','archived')),
 metadata TEXT NOT NULL,
 source_kind TEXT NOT NULL CHECK(source_kind IN ('generated','uploaded','imported')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 previous_id TEXT,
 request_id TEXT NOT NULL CHECK(length(request_id) BETWEEN 1 AND 128),
 fingerprint TEXT NOT NULL,
 PRIMARY KEY(company_id,id),
 UNIQUE(company_id,request_id),
 UNIQUE(company_id,storage_key,id),
 FOREIGN KEY(company_id,client_id) REFERENCES portal_clients(company_id,id),
 FOREIGN KEY(company_id,employee_id) REFERENCES payroll_employee_identities(company_id,employee_id),
 FOREIGN KEY(company_id,invoice_kind,invoice_id) REFERENCES portal_production(company_id,kind,id),
 FOREIGN KEY(company_id,payroll_period_kind,payroll_period_id) REFERENCES portal_production(company_id,kind,id),
 FOREIGN KEY(company_id,previous_id) REFERENCES portal_documents(company_id,id)
)'''

IMPORT_DDL = '''CREATE TABLE IF NOT EXISTS portal_excel_imports (
 company_id BIGINT NOT NULL,
 import_id TEXT NOT NULL,
 template_version TEXT NOT NULL,
 checksum TEXT NOT NULL CHECK(length(checksum)=64),
 actor_id BIGINT NOT NULL,
 actor_kind TEXT NOT NULL CHECK(actor_kind IN ('user','platform_owner')),
 created_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('applied','failed')),
 preview_summary TEXT NOT NULL,
 applied_at TEXT,
 result_counts TEXT NOT NULL,
 error_report TEXT NOT NULL,
 result_document_id TEXT NOT NULL,
 CHECK((status='applied' AND applied_at IS NOT NULL) OR (status='failed' AND applied_at IS NULL)),
 PRIMARY KEY(company_id,import_id),
 UNIQUE(company_id,checksum),
 FOREIGN KEY(company_id,result_document_id) REFERENCES portal_documents(company_id,id)
)'''


def migrate_documents(r):
    if r.dialect == 'sqlite':
        from excel_template import REQUISITES
        for table,key,extra in (('portal_company_requisites','id','director'),('portal_client_requisites','client_id','contact_person')):
            r.sql('CREATE TABLE IF NOT EXISTS '+table+' (company_id BIGINT NOT NULL,'+key+' BIGINT NOT NULL, PRIMARY KEY(company_id,'+key+'))')
            existing=r.columns(table)
            for column in REQUISITES+(extra,'updated_at','updated_by'):
                if column not in existing:r.sql('ALTER TABLE '+table+' ADD COLUMN '+column+(' BIGINT' if column=='updated_by' else ' TEXT'))
            r.sql('CREATE UNIQUE INDEX IF NOT EXISTS '+table+'_scope ON '+table+'(company_id,'+key+')')
            for event in ('INSERT','UPDATE'):
                r.sql(f'''CREATE TRIGGER IF NOT EXISTS {table}_tenant_{event.lower()} BEFORE {event} ON {table}
                    WHEN NEW.company_id!=(SELECT company_id FROM portal_tenant_identity)
                    BEGIN SELECT RAISE(ABORT,'company_id mismatch'); END''')
        # Tenant files are independent; composite keys are still checked locally.
        r.sql('CREATE UNIQUE INDEX IF NOT EXISTS documents_client_scope ON portal_clients(company_id,id)')
        r.sql(DOCUMENT_DDL)
        r.sql(IMPORT_DDL)
        r.sql('CREATE INDEX IF NOT EXISTS documents_filter ON portal_documents(company_id,status,document_type,created_at,id)')
        r.sql('CREATE INDEX IF NOT EXISTS documents_refs ON portal_documents(company_id,client_id,employee_id,document_date)')
        r.sql('CREATE INDEX IF NOT EXISTS documents_fingerprint ON portal_documents(company_id,fingerprint,status)')
        for table in ('portal_documents','portal_excel_imports'):
            for operation in ('INSERT','UPDATE'):
                r.sql(f'''CREATE TRIGGER IF NOT EXISTS {table}_tenant_{operation.lower()}
                    BEFORE {operation} ON {table} WHEN NEW.company_id IS NULL OR
                    NEW.company_id!=(SELECT company_id FROM portal_tenant_identity)
                    BEGIN SELECT RAISE(ABORT,'company_id mismatch'); END''')
            r.sql(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
                     BEGIN SELECT RAISE(ABORT,'Document/import history is immutable'); END''')
        from document_domain import COLUMNS
        changed=' OR '.join('NEW.'+column+' IS NOT OLD.'+column for column in COLUMNS if column!='status')
        r.sql("CREATE TRIGGER IF NOT EXISTS documents_archive_only BEFORE UPDATE ON portal_documents "
              "WHEN OLD.status!='ready' OR NEW.status!='archived' OR "+changed+
              " BEGIN SELECT RAISE(ABORT,'Only document archive is allowed'); END")
        r.sql('''CREATE TRIGGER IF NOT EXISTS imports_applied_immutable BEFORE UPDATE ON portal_excel_imports
            WHEN OLD.status='applied' OR NEW.checksum!=OLD.checksum OR NEW.import_id!=OLD.import_id
            BEGIN SELECT RAISE(ABORT,'Applied import is immutable'); END''')
    elif not all(r.has_table(t) for t in ('portal_documents','portal_excel_imports')):
        raise RuntimeError('Apply postgresql_stage8_documents_excel.sql with the migration operator first')
    if not r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=7',(r.company_id,)).fetchone():
        r.sql('INSERT INTO portal_production_migrations(company_id,version,applied_at) VALUES(?,7,?)',(r.company_id,utcnow()))
