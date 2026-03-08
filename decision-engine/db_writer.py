"""
db_writer.py — PostgreSQL writes for FLAG/BLOCK decisions.

Class:
    DBWriter — connection pool, write_decision(), close()
"""
import structlog
import psycopg2
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import Json

log = structlog.get_logger(__name__)


class DBWriter:
    def __init__(self, dsn: str) -> None:
        self._pool = psycopg2_pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=dsn,
        )
        log.info("db_pool_created", minconn=1, maxconn=5)

    def write_decision(
        self,
        txn_id: str,
        user_id: str,
        amount: float,
        fraud_probability: float,
        risk_level: str,
        decision: str,
        fired_rules: list,
        feature_vector: dict,
        location_lat: float | None = None,
        location_lng: float | None = None,
        processing_latency_ms: float | None = None,
    ) -> bool:
        """
        Insert any decision (APPROVE, FLAG, BLOCK) into decisions table.

        Columns written:
            transaction_id, user_id, amount, fraud_probability,
            risk_level, decision, fired_rules (JSONB), feature_vector (JSONB),
            location_lat, location_lng, processing_latency_ms

        shap_values column is left at its DEFAULT '[]'::jsonb — the
        shap-explainer service will UPDATE it asynchronously.

        Returns True on success, False on any exception (non-blocking).
        """
        if decision not in ("APPROVE", "FLAG", "BLOCK"):
            log.warning("db_write_skipped_unknown", transaction_id=txn_id, decision=decision)
            return False

        conn = None
        try:
            conn = self._pool.getconn()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO decisions
                        (transaction_id, user_id, amount, fraud_probability,
                         risk_level, decision, fired_rules, feature_vector,
                         location_lat, location_lng, processing_latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        txn_id,
                        user_id,
                        amount,
                        fraud_probability,
                        risk_level,
                        decision,
                        Json(fired_rules),
                        Json(feature_vector),
                        location_lat,
                        location_lng,
                        processing_latency_ms,
                    ),
                )
            conn.commit()
            return True
        except Exception as e:
            log.error(
                "db_write_failed",
                transaction_id=txn_id,
                decision=decision,
                error=str(e),
            )
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if conn:
                self._pool.putconn(conn)

    def close(self) -> None:
        self._pool.closeall()
        log.info("db_pool_closed")
