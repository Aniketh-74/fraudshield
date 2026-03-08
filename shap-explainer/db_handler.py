"""
db_handler.py — PostgreSQL reads and updates for SHAP computation.

Class:
    DBHandler — persistent psycopg2 connection, fetch_unprocessed(), update_shap_values()

Query pattern:
    SELECT ... FOR UPDATE SKIP LOCKED  — safe for concurrent shap-explainer instances
    UPDATE decisions SET shap_values = %s WHERE id = %s  — per-row update in batch

Transaction scope:
    fetch_unprocessed() begins an explicit transaction.
    update_shap_values() runs within that transaction.
    Caller must call commit() after processing the batch.
    On exception: caller must call rollback().
"""
import json

import psycopg2
import structlog

log = structlog.get_logger(__name__)


class DBHandler:
    def __init__(self, dsn: str) -> None:
        self._conn = psycopg2.connect(dsn=dsn)
        # Use autocommit=False (default) — we manage transactions explicitly
        self._conn.autocommit = False
        log.info("db_handler_connected")

    def fetch_unprocessed(self, limit: int = 50) -> list[dict]:
        """
        Fetch up to `limit` FLAG/BLOCK decisions where shap_values is still the
        empty default ('[]'::jsonb). Locks selected rows with SKIP LOCKED so
        concurrent shap-explainer instances don't double-process.

        Must be called at the start of a new transaction (not inside an open one).
        Returns list of {"id": int, "feature_vector": dict}.
        Returns empty list if no unprocessed rows exist.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, feature_vector
                FROM decisions
                WHERE decision IN ('FLAG', 'BLOCK')
                  AND shap_values = '[]'::jsonb
                ORDER BY created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            rows = cur.fetchall()

        result = []
        for row_id, feature_vector_raw in rows:
            # psycopg2 returns JSONB as Python dict automatically
            if isinstance(feature_vector_raw, str):
                feature_vector = json.loads(feature_vector_raw)
            else:
                feature_vector = feature_vector_raw or {}
            result.append({"id": row_id, "feature_vector": feature_vector})

        return result

    def update_shap_values(self, row_id: int, shap_values: list[dict]) -> None:
        """
        Update shap_values column for a single decision row.
        Must be called within the transaction opened by fetch_unprocessed().
        Does not commit — caller commits after the full batch.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE decisions SET shap_values = %s WHERE id = %s",
                (json.dumps(shap_values), row_id),
            )

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
        log.info("db_handler_closed")
