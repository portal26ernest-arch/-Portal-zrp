-- Isolated PostgreSQL test hardening. Apply after postgresql_runtime.sql with
-- the migration owner. Existing tenant rows and financial amounts are untouched.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Only the control role may read these per-company context keys. The ordinary
-- API tenant role receives no privileges on this table.
CREATE TABLE IF NOT EXISTS portal_company_keys (
 company_id BIGINT PRIMARY KEY REFERENCES companies(id),
 secret TEXT NOT NULL CHECK(length(secret) >= 64)
);
REVOKE ALL ON portal_company_keys FROM PUBLIC;

CREATE OR REPLACE FUNCTION portal_provision_company(cid BIGINT) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF cid IS NULL OR cid < 1 OR NOT EXISTS(SELECT 1 FROM public.companies WHERE id=cid) THEN
  RAISE EXCEPTION 'company unavailable';
 END IF;
 INSERT INTO public.portal_company_keys(company_id,secret)
 VALUES(cid,encode(public.gen_random_bytes(32),'hex')) ON CONFLICT(company_id) DO NOTHING;
 INSERT INTO public.portal_production_migrations(company_id,version,applied_at)
 VALUES(cid,3,CURRENT_TIMESTAMP::text),(cid,4,CURRENT_TIMESTAMP::text),(cid,5,CURRENT_TIMESTAMP::text)
 ON CONFLICT(company_id,version) DO NOTHING;
END;
$$;
REVOKE ALL ON FUNCTION portal_provision_company(BIGINT) FROM PUBLIC;

-- Bind a transaction to a company only after presenting the key known to the
-- control plane. The RLS proof includes the current transaction ID, so a
-- copied portal.company_id or proof cannot be reused in another transaction.
CREATE OR REPLACE FUNCTION portal_bind_company(cid BIGINT, supplied TEXT) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE stored TEXT;
BEGIN
 SELECT secret INTO stored FROM public.portal_company_keys WHERE company_id=cid;
 IF stored IS NULL OR supplied IS DISTINCT FROM stored THEN
  RAISE EXCEPTION 'company context denied';
 END IF;
 PERFORM set_config('portal.company_id',cid::text,true);
 PERFORM set_config('portal.company_proof',
  encode(public.hmac(cid::text || ':' || pg_current_xact_id()::text,stored,'sha256'),'hex'),true);
END;
$$;
REVOKE ALL ON FUNCTION portal_bind_company(BIGINT,TEXT) FROM PUBLIC;

CREATE OR REPLACE FUNCTION portal_current_company() RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE cid BIGINT; stored TEXT; expected TEXT;
BEGIN
 IF NULLIF(current_setting('portal.company_id',true),'') IS NULL OR
    current_setting('portal.company_id',true) !~ '^[0-9]+$' THEN
  RETURN NULL;
 END IF;
 cid := current_setting('portal.company_id',true)::bigint;
 SELECT secret INTO stored FROM public.portal_company_keys WHERE company_id=cid;
 IF stored IS NULL THEN RETURN NULL; END IF;
 expected := encode(public.hmac(cid::text || ':' || pg_current_xact_id()::text,stored,'sha256'),'hex');
 IF current_setting('portal.company_proof',true) IS DISTINCT FROM expected THEN RETURN NULL; END IF;
 RETURN cid;
END;
$$;
REVOKE ALL ON FUNCTION portal_current_company() FROM PUBLIC;

DO $$
DECLARE t TEXT;
BEGIN
 FOREACH t IN ARRAY ARRAY[
  'employees','app_users','app_sessions','portal_clients','portal_client_operations',
  'manager_client_assignments','work_log','payroll_payments','payroll_transactions',
  'client_invoices','client_payments','materials','material_movements',
  'operation_material_norms','production_jobs','production_job_progress','audit_log',
  'work_material_consumption'
 ] LOOP
  EXECUTE format('ALTER POLICY portal_company ON %I USING (company_id=portal_current_company()) WITH CHECK (company_id=portal_current_company())',t);
 END LOOP;
END $$;
ALTER POLICY production_company ON portal_production
 USING (company_id=portal_current_company()) WITH CHECK (company_id=portal_current_company());
ALTER POLICY production_migration_company ON portal_production_migrations
 USING (company_id=portal_current_company()) WITH CHECK (company_id=portal_current_company());

-- Generate keys for already-created synthetic companies without changing data.
SELECT portal_provision_company(id) FROM companies;

CREATE TABLE IF NOT EXISTS portal_rls_context_schema (
 version INTEGER PRIMARY KEY CHECK(version > 0),
 applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO portal_rls_context_schema(version) VALUES(1) ON CONFLICT(version) DO NOTHING;
COMMIT;
