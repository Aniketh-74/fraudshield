"""
main.py — SHAP explainer service entrypoint.

Architecture: polling service (not Kafka consumer).
Reads FLAG/BLOCK decisions from PostgreSQL with shap_values='[]',
computes top-5 SHAP values, writes them back.
Runs as a background worker — does not block the decision-engine consumer loop.

Startup order:
    1. Configure structlog JSON logging
    2. Load ShapComputer (model.txt + feature_order.json)
    3. Connect DBHandler
    4. Register SIGTERM/SIGINT handler
    5. Poll loop until stop_event set
    6. Close DBHandler
"""
import signal
import threading

import structlog

import config
from shap_computer import ShapComputer
from db_handler import DBHandler

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger(__name__)

_stop_event = threading.Event()


def _signal_handler(sig, frame) -> None:
    log.info("shutdown_signal_received", signal=sig)
    _stop_event.set()


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def main() -> None:
    log.info(
        "shap_explainer_starting",
        model_txt=config.MODEL_TXT_PATH,
        feature_order=config.FEATURE_ORDER_PATH,
        poll_interval=config.SHAP_POLL_INTERVAL_SECONDS,
        batch_size=config.SHAP_BATCH_SIZE,
    )

    # Load model artifacts once at startup
    computer = ShapComputer(
        model_txt_path=config.MODEL_TXT_PATH,
        feature_order_path=config.FEATURE_ORDER_PATH,
    )

    db = DBHandler(dsn=config.DATABASE_URL)

    try:
        _poll_loop(computer, db)
    finally:
        db.close()
        log.info("shap_explainer_stopped")


def _poll_loop(computer: ShapComputer, db: DBHandler) -> None:
    """
    Polling loop:
        1. fetch_unprocessed(limit=SHAP_BATCH_SIZE) — SELECT ... FOR UPDATE SKIP LOCKED
        2. For each row: compute SHAP, update_shap_values()
        3. commit() after the full batch
        4. If no rows: wait SHAP_POLL_INTERVAL_SECONDS (interruptible by stop_event)
        5. If stop_event set: exit loop

    Error handling:
        - Exception during a batch: rollback(), log error, wait, continue
        - ShapComputer.compute() error for a single row: log, skip that row,
          leave shap_values='[]' (will be retried on next poll)
    """
    log.info("poll_loop_started")
    batch_count = 0

    while not _stop_event.is_set():
        try:
            rows = db.fetch_unprocessed(limit=config.SHAP_BATCH_SIZE)

            if not rows:
                log.debug("no_unprocessed_rows", waiting_seconds=config.SHAP_POLL_INTERVAL_SECONDS)
                _stop_event.wait(timeout=config.SHAP_POLL_INTERVAL_SECONDS)
                continue

            computed_count = 0
            failed_count = 0

            for row in rows:
                row_id = row["id"]
                feature_vector = row["feature_vector"]

                try:
                    shap_values = computer.compute(feature_vector)
                    db.update_shap_values(row_id, shap_values)
                    computed_count += 1
                    log.debug(
                        "shap_computed",
                        id=row_id,
                        top_feature=shap_values[0]["feature"] if shap_values else None,
                        top_value=shap_values[0]["value"] if shap_values else None,
                    )
                except Exception as e:
                    log.error(
                        "shap_compute_failed",
                        id=row_id,
                        error=str(e),
                    )
                    failed_count += 1
                    # Continue processing remaining rows in batch
                    # Failed rows are skipped (shap_values stays '[]', retried next poll)

            db.commit()
            batch_count += 1
            log.info(
                "batch_committed",
                batch=batch_count,
                computed=computed_count,
                failed=failed_count,
                total_in_batch=len(rows),
            )

        except Exception as e:
            log.error("poll_batch_error", error=str(e))
            try:
                db.rollback()
            except Exception:
                pass
            # Wait before retrying to avoid tight error loop
            _stop_event.wait(timeout=config.SHAP_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
