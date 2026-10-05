-- Extend employee access roles without rewriting the immutable Stage 10 migration.
BEGIN;
ALTER TABLE portal_access_invites
  DROP CONSTRAINT IF EXISTS portal_access_invites_role_check;
ALTER TABLE portal_access_invites
  ADD CONSTRAINT portal_access_invites_role_check
  CHECK(role IN ('admin','director','manager','packer','loader','driver','shift','accountant'));
COMMIT;
