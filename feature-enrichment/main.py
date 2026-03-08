"""
main.py — Entry point for the feature-enrichment service.

Startup sequence:
    1. Configure structlog (JSON output for Docker)
    2. Wait for Redis (build_redis_client with retry)
    3. Wait for Kafka (wait_for_kafka_consumer with list_topics probe)
    4. Run consumer loop (blocks until SIGTERM/SIGINT)
"""
import structlog

import config
from redis_client import build_redis_client
from kafka_consumer import wait_for_kafka_consumer, run_consumer_loop


def configure_logging() -> None:
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


def main() -> None:
    configure_logging()
    log = structlog.get_logger(__name__)
    log.info("feature_enrichment_starting", kafka=config.KAFKA_BOOTSTRAP_SERVERS, redis=config.REDIS_URL)

    r = build_redis_client()
    consumer, producer = wait_for_kafka_consumer()
    run_consumer_loop(consumer, producer, r)
    log.info("feature_enrichment_stopped")


if __name__ == "__main__":
    main()
