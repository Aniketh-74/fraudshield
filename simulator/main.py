"""
main.py — Transaction simulator entry point.

Startup sequence:
  1. Configure structlog JSON logging (MUST be first)
  2. Set up SIGTERM/SIGINT signal handlers
  3. Initialize registries, fraud injector, CSV writer
  4. Wait for Kafka with retry (exits non-zero if broker unreachable)
  5. Main loop: generate -> inject fraud -> produce to Kafka -> write CSV
  6. Graceful shutdown on stop_event: flush CSV, drain Kafka queue

Usage:
  python main.py

  # All configuration via environment variables — see .env.example
"""
import logging
import random
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import structlog

# NOTE: configure_logging() MUST be called before any other import that uses structlog.
# It is defined here and called before module-level logger assignment.


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON output (Kubernetes-compatible).

    Call this as the very first statement in main.py before any other
    module initialises a logger.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )


# ── Imports that may use structlog at module level ─────────────────────────
import config  # noqa: E402  (must come after configure_logging is defined)
from models import Transaction, MerchantRegistry, UserRegistry  # noqa: E402
from fraud_patterns import FraudInjector  # noqa: E402
from kafka_producer import wait_for_kafka, produce_transaction, flush_producer  # noqa: E402
from csv_writer import CSVWriter, CSV_FIELDNAMES  # noqa: E402

# ── Module-level stop event and logger ────────────────────────────────────
stop_event = threading.Event()
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

def _handle_sigterm(signum, frame) -> None:
    """SIGTERM/SIGINT handler — sets stop flag for main loop.

    Do NOT perform I/O here. Only set the event and return immediately.
    The main loop will detect stop_event.is_set() and run the shutdown sequence.
    """
    stop_event.set()


def setup_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)


# ---------------------------------------------------------------------------
# Transaction generation
# ---------------------------------------------------------------------------

def generate_base_txn(
    user_id: str,
    user_registry: UserRegistry,
    merchant_registry: MerchantRegistry,
    rng: random.Random,
    now_utc: datetime,
) -> dict:
    """Generate base transaction fields before fraud injection.

    Returns a dict with all fields EXCEPT is_fraud (added by FraudInjector).
    """
    profile = user_registry.get_profile(user_id)

    # Pick merchant: 70% chance from user's usual categories, 30% random
    if rng.random() < 0.70 and profile.usual_merchant_categories:
        category = rng.choice(profile.usual_merchant_categories)
        merchant_id = merchant_registry.random_merchant_for_category(category, rng)
        merchant_category = category
    else:
        merchant_id = merchant_registry.random_merchant(rng)
        merchant_category = merchant_registry.get_category(merchant_id)

    # Location: home city centre with ±0.05 degree jitter
    from cities import CITIES
    home = CITIES[profile.home_city]
    latitude = home["lat"] + rng.uniform(-0.05, 0.05)
    longitude = home["lng"] + rng.uniform(-0.05, 0.05)

    # Amount: Gaussian around avg_spend, minimum ₹1
    amount = max(1.0, rng.gauss(profile.avg_spend, profile.std_dev))
    amount = round(amount, 2)

    return {
        "transaction_id": uuid.uuid4().hex,
        "user_id": user_id,
        "merchant_id": merchant_id,
        "amount": amount,
        "currency": "INR",
        "merchant_category": merchant_category,
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "timestamp": now_utc.isoformat(),
        "device_id": uuid.uuid4().hex,
        "is_international": False,
    }


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def _emit_transaction(
    txn_fields: dict,
    user_id: str,
    producer,
    csv_writer: CSVWriter,
    user_registry: UserRegistry,
    now_utc: datetime,
) -> None:
    """Build Transaction, update user state, produce to Kafka, write to CSV."""
    txn = Transaction(**txn_fields)
    user_registry.update_state(
        user_id, txn.latitude, txn.longitude, now_utc.timestamp()
    )
    produce_transaction(producer, config.KAFKA_TOPIC, txn.to_kafka_dict())
    csv_writer.add(txn.to_csv_dict())
    logger.debug(
        "transaction_generated",
        transaction_id=txn.transaction_id,
        user_id=txn.user_id,
        is_fraud=txn.is_fraud,
    )


def run() -> None:
    """Main entry point: initialise services and run the transaction loop."""
    configure_logging(config.LOG_LEVEL)
    setup_signal_handlers()

    # Seed randomness
    rng = random.Random(config.RANDOM_SEED) if config.RANDOM_SEED is not None else random.Random()

    # Build registries
    user_registry = UserRegistry(config, rng)
    merchant_registry = MerchantRegistry()
    fraud_injector = FraudInjector(config, user_registry, merchant_registry, rng)

    # CSV writer
    csv_writer = CSVWriter(config.DATA_OUTPUT_PATH, config.OVERWRITE_CSV, CSV_FIELDNAMES)

    # Wait for Kafka (exits non-zero if unavailable after all retries)
    producer = wait_for_kafka(
        config.KAFKA_BOOTSTRAP_SERVERS,
        config.KAFKA_RETRY_ATTEMPTS,
        config.KAFKA_RETRY_INTERVAL_SECONDS,
    )

    logger.info(
        "simulator_started",
        txn_rate=config.TXN_RATE,
        fraud_rate=config.FRAUD_RATE,
        num_users=config.NUM_USERS,
        num_merchants=config.NUM_MERCHANTS,
        data_output_path=config.DATA_OUTPUT_PATH,
    )

    # ── Main loop ────────────────────────────────────────────────────────
    while not stop_event.is_set():
        user_id = user_registry.random_user_id(rng)
        now_utc = datetime.now(timezone.utc)

        # Generate base transaction fields (no is_fraud yet)
        base_fields = generate_base_txn(user_id, user_registry, merchant_registry, rng, now_utc)

        # Apply fraud injection (adds is_fraud key)
        final_fields = fraud_injector.try_inject_fraud(base_fields, now_utc)

        # Emit the primary transaction
        _emit_transaction(final_fields, user_id, producer, csv_writer, user_registry, now_utc)

        # ── Rapid-fire burst handling ────────────────────────────────────
        # After a rapid-fire injection, emit remaining burst transactions
        # with random 5-20 second gaps before the regular sleep.
        while fraud_injector.has_pending_burst() and not stop_event.is_set():
            burst_sleep = rng.uniform(5, 20)
            time.sleep(burst_sleep)

            burst_txn = fraud_injector.pop_burst_txn()
            if burst_txn is None:
                break
            burst_now = datetime.now(timezone.utc)
            # Refresh timestamp for the burst transaction
            burst_txn["timestamp"] = burst_now.isoformat()
            burst_txn["transaction_id"] = uuid.uuid4().hex
            burst_txn["device_id"] = uuid.uuid4().hex
            _emit_transaction(burst_txn, user_id, producer, csv_writer, user_registry, burst_now)

        # Regular rate control sleep
        time.sleep(1.0 / config.TXN_RATE)

    # ── Shutdown sequence ────────────────────────────────────────────────
    logger.info("shutdown_started")
    csv_writer.flush_remaining()
    flush_producer(producer)
    logger.info("shutdown_complete")


if __name__ == "__main__":
    run()
