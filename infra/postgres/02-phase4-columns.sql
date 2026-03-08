-- 02-phase4-columns.sql
-- Adds fired_rules, feature_vector, shap_values columns to decisions table.
-- Safe to run multiple times (IF NOT EXISTS guards).
-- Fresh install: mounted at /docker-entrypoint-initdb.d/02-phase4-columns.sql
-- Existing install (postgres_data volume already exists):
--   docker exec postgres psql -U postgres -d frauddb -f /02-phase4-columns.sql

ALTER TABLE decisions
  ADD COLUMN IF NOT EXISTS fired_rules    JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS feature_vector JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS shap_values    JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_decisions_fired_rules
  ON decisions USING gin(fired_rules);

CREATE INDEX IF NOT EXISTS idx_decisions_decision
  ON decisions(decision);
