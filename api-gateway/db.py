"""
db.py — asyncpg connection pool and query functions for API Gateway.
"""
import json
import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def _init_connection(conn):
    """Register JSON/JSONB codecs so asyncpg returns dicts/lists, not strings."""
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool."""
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, init=_init_connection)
    log.info("db_pool_created", min_size=2, max_size=10)
    return pool


async def get_recent_transactions(pool, limit: int = 100) -> list[dict]:
    """
    Return the last N decisions ordered by created_at DESC.
    Includes all columns needed by the live feed.
    """
    rows = await pool.fetch(
        """
        SELECT transaction_id, user_id, amount, fraud_probability,
               risk_level, decision, fired_rules, created_at,
               location_lat, location_lng
        FROM decisions
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_transaction_by_id(pool, txn_id: str) -> dict | None:
    """
    Return full decision row including shap_values and analyst_decision fields.
    Returns None if not found.
    """
    row = await pool.fetchrow(
        """
        SELECT transaction_id, user_id, amount, fraud_probability,
               risk_level, decision, fired_rules, feature_vector,
               shap_values, created_at, location_lat, location_lng,
               analyst_decision, analyst_id, reviewed_at,
               processing_latency_ms
        FROM decisions
        WHERE transaction_id = $1
        """,
        txn_id,
    )
    if row is None:
        return None
    return dict(row)


async def get_metrics_summary(pool) -> dict:
    """
    Return aggregate metrics:
      total_transactions, fraud_rate (% FLAG+BLOCK), blocked_count,
      avg_latency_ms, review_queue_count (FLAG + analyst_decision IS NULL).
    """
    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_transactions,
            COALESCE(
                SUM(CASE WHEN decision IN ('FLAG', 'BLOCK') THEN 1 ELSE 0 END)::float
                / NULLIF(COUNT(*), 0),
                0.0
            ) AS fraud_rate,
            SUM(CASE WHEN decision = 'FLAG' THEN 1 ELSE 0 END)::int AS flagged_count,
            SUM(CASE WHEN decision = 'BLOCK' THEN 1 ELSE 0 END)::int AS blocked_count,
            SUM(CASE WHEN decision = 'APPROVE' THEN 1 ELSE 0 END)::int AS approved_count,
            COALESCE(AVG(processing_latency_ms), 0.0) AS avg_latency_ms,
            SUM(CASE WHEN decision = 'FLAG' AND analyst_decision IS NULL THEN 1 ELSE 0 END)::int
                AS review_queue_count
        FROM decisions
        """
    )
    return dict(row)


async def get_flagged_transactions(pool) -> list[dict]:
    """Return FLAG transactions not yet reviewed, newest first."""
    rows = await pool.fetch(
        """
        SELECT transaction_id, user_id, amount, fraud_probability,
               risk_level, decision, fired_rules, created_at,
               location_lat, location_lng
        FROM decisions
        WHERE decision = 'FLAG' AND analyst_decision IS NULL
        ORDER BY created_at DESC
        LIMIT 100
        """
    )
    return [dict(r) for r in rows]


async def get_hourly_stats(pool) -> list[dict]:
    """
    Return per-hour decision counts for the last 24 hours.
    Columns: hour (timestamp), decision, count.
    """
    rows = await pool.fetch(
        """
        SELECT
            date_trunc('hour', created_at) AS hour,
            decision,
            COUNT(*)::int AS count
        FROM decisions
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2 ASC
        """
    )
    return [dict(r) for r in rows]


async def record_review(pool, txn_id: str, decision: str, analyst_id: str) -> bool:
    """
    Update analyst_decision, analyst_id, and reviewed_at for a transaction.
    Returns True on success.
    """
    await pool.execute(
        """
        UPDATE decisions
        SET analyst_decision = $1,
            analyst_id       = $2,
            reviewed_at      = NOW()
        WHERE transaction_id = $3
        """,
        decision,
        analyst_id,
        txn_id,
    )
    return True
