-- Stage 10: tenant-scoped, hash-only one-time access invitations.
-- Invited accounts are inactive until explicit company administrator approval.
BEGIN;
CREATE TABLE IF NOT EXISTS portal_access_invites (
 company_id BIGINT NOT NULL DEFAULT portal_current_company(),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128),
 token_hash TEXT NOT NULL CHECK(length(token_hash)=64),
 created_by BIGINT NOT NULL CHECK(created_by>0),
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','accepted','approved','revoked','expired','rejected')),
 role TEXT NOT NULL CHECK(role IN ('admin','director','manager','packer','shift','accountant')),
 username TEXT NOT NULL CHECK(length(trim(username)) BETWEEN 1 AND 100),
 display_name TEXT NOT NULL CHECK(length(trim(display_name)) BETWEEN 1 AND 100),
 employee_id BIGINT,
 request_id TEXT NOT NULL CHECK(length(request_id) BETWEEN 1 AND 128),
 user_id BIGINT,
 accepted_at TEXT,
 decided_at TEXT,
 decided_by BIGINT,
 PRIMARY KEY(company_id,id),
 UNIQUE(company_id,token_hash),
 UNIQUE(company_id,request_id),
 FOREIGN KEY(company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS portal_access_invites_status ON portal_access_invites(company_id,status,created_at DESC);
ALTER TABLE portal_access_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_access_invites FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS portal_company_access_invites ON portal_access_invites;
CREATE POLICY portal_company_access_invites ON portal_access_invites
 USING(company_id=portal_current_company()) WITH CHECK(company_id=portal_current_company());

CREATE OR REPLACE FUNCTION portal_access_invite_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'invitation history is immutable'; END IF;
 IF NEW.company_id IS DISTINCT FROM OLD.company_id OR NEW.id IS DISTINCT FROM OLD.id
  OR NEW.token_hash IS DISTINCT FROM OLD.token_hash OR NEW.created_by IS DISTINCT FROM OLD.created_by
  OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
  OR NEW.role IS DISTINCT FROM OLD.role OR NEW.username IS DISTINCT FROM OLD.username
  OR NEW.display_name IS DISTINCT FROM OLD.display_name OR NEW.employee_id IS DISTINCT FROM OLD.employee_id
  OR NEW.request_id IS DISTINCT FROM OLD.request_id
  OR NOT ((OLD.status='pending' AND NEW.status IN ('accepted','revoked','expired'))
       OR (OLD.status='accepted' AND NEW.status IN ('approved','revoked','rejected')))
 THEN RAISE EXCEPTION 'invalid invitation transition'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS portal_access_invite_guard ON portal_access_invites;
CREATE TRIGGER portal_access_invite_guard BEFORE UPDATE OR DELETE ON portal_access_invites
 FOR EACH ROW EXECUTE FUNCTION portal_access_invite_guard();
REVOKE ALL ON portal_access_invites FROM PUBLIC;
INSERT INTO portal_production_migrations(company_id,version,applied_at)
 SELECT id,10,CURRENT_TIMESTAMP::text FROM companies
 ON CONFLICT(company_id,version) DO NOTHING;
COMMIT;
