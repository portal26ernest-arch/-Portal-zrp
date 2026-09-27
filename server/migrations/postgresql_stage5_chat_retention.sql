-- PORTAL 3.2: retention cleanup for expiring chat rows only.
-- Financial, payroll, document and production history remains immutable.
BEGIN;

CREATE OR REPLACE FUNCTION portal_production_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.kind IN ('chat_messages','chat_pins','chat_attachments') THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'production history is immutable';
    END IF;

    IF OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers')
       OR OLD.id <> NEW.id
       OR OLD.company_id <> NEW.company_id
       OR OLD.kind <> NEW.kind
       OR OLD.created_at <> NEW.created_at THEN
        RAISE EXCEPTION 'production history is immutable';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS production_immutable ON portal_production;
CREATE TRIGGER production_immutable
BEFORE UPDATE OR DELETE ON portal_production
FOR EACH ROW EXECUTE FUNCTION portal_production_immutable();

INSERT INTO portal_production_migrations(company_id,version,applied_at)
SELECT id,5,CURRENT_TIMESTAMP::text
FROM companies
ON CONFLICT (company_id,version) DO NOTHING;

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

COMMIT;
