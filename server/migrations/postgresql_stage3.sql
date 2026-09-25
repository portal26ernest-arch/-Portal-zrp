-- Stage 3 storage schema for a future PostgreSQL deployment.
-- Apply explicitly to an isolated PORTAL database with a migration role.
-- The application role must NOT own tables, be superuser or have BYPASSRLS.
BEGIN;
CREATE TABLE IF NOT EXISTS portal_production_migrations (
    company_id BIGINT NOT NULL CHECK (company_id > 0),
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY(company_id, version)
);
CREATE TABLE IF NOT EXISTS portal_production (
    company_id BIGINT NOT NULL CHECK (company_id > 0),
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(company_id, kind, id),
    CHECK ((payload::jsonb ->> 'company_id')::bigint = company_id),
    CHECK (payload::jsonb ->> 'id' = id)
);
CREATE INDEX IF NOT EXISTS portal_production_lookup
    ON portal_production(company_id, kind, created_at);
CREATE OR REPLACE FUNCTION portal_production_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'production history is immutable';
    END IF;
    IF OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers')
       OR OLD.id <> NEW.id OR OLD.company_id <> NEW.company_id OR OLD.kind <> NEW.kind THEN
        RAISE EXCEPTION 'production history is immutable';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS production_immutable ON portal_production;
CREATE TRIGGER production_immutable BEFORE UPDATE OR DELETE ON portal_production
    FOR EACH ROW EXECUTE FUNCTION portal_production_immutable();
ALTER TABLE portal_production ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_production FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS production_company ON portal_production;
CREATE POLICY production_company ON portal_production
    USING (company_id = NULLIF(current_setting('portal.company_id', true),'')::bigint)
    WITH CHECK (company_id = NULLIF(current_setting('portal.company_id', true),'')::bigint);
ALTER TABLE portal_production_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_production_migrations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS production_migration_company ON portal_production_migrations;
CREATE POLICY production_migration_company ON portal_production_migrations
    USING (company_id = NULLIF(current_setting('portal.company_id', true),'')::bigint)
    WITH CHECK (company_id = NULLIF(current_setting('portal.company_id', true),'')::bigint);
COMMIT;
ALTER TABLE app_sessions ADD COLUMN IF NOT EXISTS portal_activity_id TEXT;
-- Import immutable snapshots with their original IDs, amounts and timestamps.
-- Migrate catalogs/auth/control-plane separately, reconcile before cutover.
