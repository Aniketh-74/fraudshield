-- 03-phase5-review-columns.sql
-- Adds analyst review columns, location columns, and latency column to decisions table.
-- Safe to run multiple times (IF NOT EXISTS guards).
-- Fresh install: mounted at /docker-entrypoint-initdb.d/03-phase5-review-columns.sql
-- Existing install (postgres_data volume exists):
--   docker exec postgres psql -U postgres -d frauddb -f /03-phase5-review-columns.sql

ALTER TABLE decisions
  ADD COLUMN IF NOT EXISTS analyst_decision     VARCHAR(20)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS analyst_id           VARCHAR(50)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS reviewed_at          TIMESTAMPTZ  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS location_lat         FLOAT        DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS location_lng         FLOAT        DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS processing_latency_ms FLOAT       DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_decisions_analyst_decision
  ON decisions(analyst_decision);

CREATE INDEX IF NOT EXISTS idx_decisions_decision_analyst
  ON decisions(decision, analyst_decision)
  WHERE analyst_decision IS NULL;
