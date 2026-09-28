-- Additive Documents/Excel schema; after Stage 6 and Stage 4c.
-- No existing migrations, catalog rates or financial snapshots are rewritten.
BEGIN;
CREATE TABLE IF NOT EXISTS portal_documents (
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
 metadata JSONB NOT NULL CHECK(jsonb_typeof(metadata)='object'),
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
);
CREATE TABLE IF NOT EXISTS portal_excel_imports (
 company_id BIGINT NOT NULL,
 import_id TEXT NOT NULL,
 template_version TEXT NOT NULL,
 checksum TEXT NOT NULL CHECK(length(checksum)=64),
 actor_id BIGINT NOT NULL,
 actor_kind TEXT NOT NULL CHECK(actor_kind IN ('user','platform_owner')),
 created_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('applied','failed')),
 preview_summary JSONB NOT NULL CHECK(jsonb_typeof(preview_summary)='object'),
 applied_at TEXT,
 result_counts JSONB NOT NULL CHECK(jsonb_typeof(result_counts)='object'),
 error_report JSONB NOT NULL CHECK(jsonb_typeof(error_report)='array'),
 result_document_id TEXT NOT NULL,
 CHECK((status='applied' AND applied_at IS NOT NULL) OR (status='failed' AND applied_at IS NULL)),
 PRIMARY KEY(company_id,import_id),
 UNIQUE(company_id,checksum),
 FOREIGN KEY(company_id,result_document_id) REFERENCES portal_documents(company_id,id)
);

CREATE INDEX IF NOT EXISTS documents_filter ON portal_documents(company_id,status,document_type,created_at,id);
CREATE INDEX IF NOT EXISTS documents_refs ON portal_documents(company_id,client_id,employee_id,document_date);
CREATE INDEX IF NOT EXISTS documents_fingerprint ON portal_documents(company_id,fingerprint,status);
CREATE INDEX IF NOT EXISTS imports_actor ON portal_excel_imports(company_id,actor_id,created_at);
ALTER TABLE portal_documents ALTER COLUMN company_id SET DEFAULT portal_current_company();
ALTER TABLE portal_excel_imports ALTER COLUMN company_id SET DEFAULT portal_current_company();
ALTER TABLE portal_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_documents FORCE ROW LEVEL SECURITY;
ALTER TABLE portal_excel_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_excel_imports FORCE ROW LEVEL SECURITY;
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['portal_documents','portal_excel_imports'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_policy WHERE polrelid=t::regclass AND polname='portal_company') THEN
   EXECUTE format('CREATE POLICY portal_company ON %I USING (company_id=portal_current_company()) WITH CHECK (company_id=portal_current_company())',t);
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid=t::regclass AND conname=t||'_company_fk') THEN
   EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY(company_id) REFERENCES companies(id)',t,t||'_company_fk');
  END IF;
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION portal_document_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$ BEGIN
 IF TG_OP='UPDATE' AND OLD.status='ready' AND NEW.status='archived'
    AND to_jsonb(NEW)-'status'=to_jsonb(OLD)-'status' THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Only document archive is allowed';
END $$;
CREATE OR REPLACE FUNCTION portal_import_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$ BEGIN
 IF TG_OP='UPDATE' AND OLD.status='failed' AND NEW.status IN ('failed','applied')
    AND NEW.company_id=OLD.company_id AND NEW.import_id=OLD.import_id
    AND NEW.checksum=OLD.checksum AND NEW.template_version=OLD.template_version THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Applied import history is immutable';
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='portal_documents'::regclass AND tgname='document_immutable') THEN
  CREATE TRIGGER document_immutable BEFORE UPDATE OR DELETE ON portal_documents FOR EACH ROW EXECUTE FUNCTION portal_document_immutable();
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='portal_excel_imports'::regclass AND tgname='import_immutable') THEN
  CREATE TRIGGER import_immutable BEFORE UPDATE OR DELETE ON portal_excel_imports FOR EACH ROW EXECUTE FUNCTION portal_import_immutable();
 END IF;
END $$;
REVOKE ALL ON portal_documents,portal_excel_imports FROM PUBLIC;
REVOKE ALL ON FUNCTION portal_document_immutable(),portal_import_immutable() FROM PUBLIC;
-- Grant only to existing restricted tenant LOGIN roles with ledger write access.
DO $$ DECLARE r RECORD; BEGIN
 FOR r IN SELECT rolname FROM pg_roles WHERE rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND has_table_privilege(rolname,'portal_production','INSERT') LOOP
  EXECUTE format('GRANT SELECT,INSERT,UPDATE ON portal_documents,portal_excel_imports TO %I',r.rolname);
 END LOOP;
END $$;
INSERT INTO portal_production_migrations(company_id,version,applied_at)
SELECT id,7,CURRENT_TIMESTAMP::text FROM companies ON CONFLICT(company_id,version) DO NOTHING;
CREATE OR REPLACE FUNCTION portal_provision_company(cid BIGINT) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN
 IF cid IS NULL OR cid<1 OR NOT EXISTS(SELECT 1 FROM public.companies WHERE id=cid) THEN RAISE EXCEPTION 'Компания недоступна'; END IF;
 INSERT INTO public.portal_company_keys(company_id,secret)
 VALUES(cid,encode(public.gen_random_bytes(32),'hex')) ON CONFLICT(company_id) DO NOTHING;
 INSERT INTO public.portal_production_migrations(company_id,version,applied_at)
 VALUES(cid,3,CURRENT_TIMESTAMP::text),(cid,4,CURRENT_TIMESTAMP::text),(cid,5,CURRENT_TIMESTAMP::text),
       (cid,6,CURRENT_TIMESTAMP::text),(cid,7,CURRENT_TIMESTAMP::text) ON CONFLICT(company_id,version) DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION portal_provision_company(BIGINT) FROM PUBLIC;
COMMIT;
