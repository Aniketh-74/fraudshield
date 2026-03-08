"""
main.py — Decision engine service entrypoint.

Startup order:
    1. Configure structlog JSON logging
    2. Start WebSocket broadcaster (daemon thread)
    3. Initialize RulesEngine (loads rules.yaml + starts watchdog)
    4. Initialize ScorerClient (persistent httpx.Client)
    5. Initialize DBWriter (psycopg2 connection pool)
    6. Wait for Kafka connectivity (retry loop)
    7. Run consumer loop (blocks until SIGTERM/SIGINT)
    8. Cleanup: close scorer_client, db_writer
"""
import structlog

import config
from rules_engine import RulesEngine
from scorer_client import ScorerClient
from db_writer import DBWriter
from ws_broadcaster import WSBroadcaster
from kafka_consumer import wait_for_kafka_consumer, run_consumer_loop

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


def main() -> None:
    log.info(
        "decision_engine_starting",
        scorer_url=config.SCORER_URL,
        input_topic=config.KAFKA_INPUT_TOPIC,
        output_topic=config.KAFKA_OUTPUT_TOPIC,
        ws_port=config.WS_PORT,
        rules_config=config.RULES_CONFIG_PATH,
    )

    # 1. Start WebSocket broadcaster
    ws = WSBroadcaster()
    ws.start(host=config.WS_HOST, port=config.WS_PORT)

    # 2. Load business rules (+ start watchdog hot-reload thread)
    rules_engine = RulesEngine(config.RULES_CONFIG_PATH)

    # 3. Initialize ML scorer client
    scorer = ScorerClient(config.SCORER_URL)

    # 4. Initialize DB writer
    db = DBWriter(config.DATABASE_URL)

    try:
        # 5. Wait for Kafka and get consumer + producer
        consumer, producer = wait_for_kafka_consumer()

        # 6. Run main loop (blocks until SIGTERM/SIGINT)
        run_consumer_loop(
            consumer=consumer,
            producer=producer,
            rules_engine=rules_engine,
            scorer_client=scorer,
            db_writer=db,
            ws_broadcaster=ws,
        )
    finally:
        scorer.close()
        db.close()
        log.info("decision_engine_stopped")


if __name__ == "__main__":
    main()
