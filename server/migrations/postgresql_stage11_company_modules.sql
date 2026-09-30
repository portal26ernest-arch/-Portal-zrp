-- Additive company feature flags. An empty map preserves all existing behavior.
BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS module_toggles TEXT NOT NULL DEFAULT '{}';

COMMIT;
