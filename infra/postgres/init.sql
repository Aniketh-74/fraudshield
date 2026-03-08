-- init.sql: Initial schema for fraud detection pipeline
-- Mounted at: /docker-entrypoint-initdb.d/01-schema.sql
-- Runs once on first container start with empty data directory.
-- All IF NOT EXISTS guards make this script idempotent.

-- Main decisions table: stores every BLOCK and FLAG decision
-- APPROVE decisions are NOT stored (design decision: flagged/blocked only at scale)
CREATE TABLE IF NOT EXISTS decisions (
    id               SERIAL PRIMARY KEY,
    transaction_id   VARCHAR(50)    NOT NULL,
    user_id          VARCHAR(20)    NOT NULL,
    amount           NUMERIC(12, 2) NOT NULL,
    fraud_probability FLOAT         NOT NULL,
    risk_level       VARCHAR(10)    NOT NULL,  -- LOW | MEDIUM | HIGH
    decision         VARCHAR(10)    NOT NULL,  -- APPROVE | FLAG | BLOCK
    created_at       TIMESTAMP      DEFAULT NOW()
);

-- Extended transactions table for full feature storage (Phase 4 DECN-05)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id    VARCHAR(64)    PRIMARY KEY,
    user_id           VARCHAR(32)    NOT NULL,
    merchant_id       VARCHAR(32),
    amount            NUMERIC(12, 2),
    merchant_category VARCHAR(32),
    timestamp         TIMESTAMPTZ,
    fraud_probability NUMERIC(6, 4),
    risk_level        VARCHAR(16),
    decision          VARCHAR(16),
    rules_triggered   JSONB,
    feature_vector    JSONB,
    created_at        TIMESTAMPTZ    DEFAULT NOW()
);

-- Indexes for common query patterns (Phase 5 API gateway)
CREATE INDEX IF NOT EXISTS idx_transactions_user_id
    ON transactions(user_id);

CREATE INDEX IF NOT EXISTS idx_transactions_timestamp
    ON transactions(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_risk_level
    ON transactions(risk_level);

CREATE INDEX IF NOT EXISTS idx_transactions_decision
    ON transactions(decision);

CREATE INDEX IF NOT EXISTS idx_decisions_created_at
    ON decisions(created_at DESC);
