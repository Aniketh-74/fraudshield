"""
kafka_consumer.py — Confluent Kafka consumer + producer for feature enrichment.

Functions:
    build_consumer         — Create configured Consumer instance.
    build_output_producer  — Create configured Producer for enriched-transactions.
    wait_for_kafka_consumer — Startup probe using list_topics() (same pattern as simulator).
    run_consumer_loop      — Main poll loop: consume -> compute -> produce -> commit.
"""
import json
import signal
import sys
import time

import redis
import structlog
from confluent_kafka import Consumer, Producer, KafkaException, KafkaError

import config
from feature_computer import read_user_state, compute_and_write

log = structlog.get_logger(__name__)

_running = True


def _signal_handler(sig, frame):
    global _running
    log.info("shutdown_signal_received", signal=sig)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def build_consumer() -> Consumer:
    """
    Create a Consumer with production-grade settings.

    group.id: "feature-enrichment-group" (from config.KAFKA_GROUP_ID)
    auto.offset.reset: "earliest" — replay from start if no committed offset
    enable.auto.commit: false — manual commit after Redis write + produce
    max.poll.interval.ms: 300000 — 5 min; adequate for Redis + produce latency
    session.timeout.ms: 30000
    heartbeat.interval.ms: 10000
    """
    return Consumer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": config.KAFKA_GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "max.poll.interval.ms": 300000,
        "session.timeout.ms": 30000,
        "heartbeat.interval.ms": 10000,
    })


def build_output_producer() -> Producer:
    """
    Create a Producer for publishing to enriched-transactions.
    Same configuration as simulator/kafka_producer.py build_producer().
    """
    return Producer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",
        "linger.ms": 5,
        "compression.type": "lz4",
        "batch.size": 65536,
        "queue.buffering.max.messages": 100000,
        "delivery.report.only.error": False,
    })


def _delivery_callback(err, msg) -> None:
    if err:
        log.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        log.debug(
            "kafka_delivered",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


def wait_for_kafka_consumer() -> tuple[Consumer, Producer]:
    """
    Probe Kafka broker using list_topics() before starting the consumer loop.
    Returns (consumer, producer) on success. Calls sys.exit(1) on exhaustion.

    Mirrors simulator/kafka_producer.py wait_for_kafka() exactly.
    """
    for attempt in range(1, config.KAFKA_RETRY_ATTEMPTS + 1):
        try:
            probe = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS})
            probe.list_topics(timeout=5)
            log.info("kafka_connected", attempt=attempt)
            return build_consumer(), build_output_producer()
        except KafkaException as e:
            log.warning(
                "kafka_unavailable",
                attempt=attempt,
                max_attempts=config.KAFKA_RETRY_ATTEMPTS,
                error=str(e),
            )
            if attempt < config.KAFKA_RETRY_ATTEMPTS:
                time.sleep(config.KAFKA_RETRY_INTERVAL_SECONDS)

    log.error("kafka_connection_exhausted", max_attempts=config.KAFKA_RETRY_ATTEMPTS)
    sys.exit(1)


def run_consumer_loop(
    consumer: Consumer,
    producer: Producer,
    r: redis.Redis,
) -> None:
    """
    Main consumer poll loop.

    Flow per message:
        1. consumer.poll(timeout=1.0)
        2. Deserialize JSON -> txn dict
        3. read_user_state(r, user_id)
        4. compute_and_write(r, txn, prior_state) -> features
        5. Merge txn + features -> enriched message
        6. producer.produce(KAFKA_OUTPUT_TOPIC, value=enriched_json, key=user_id)
        7. producer.poll(0)
        8. Every KAFKA_MIN_COMMIT_COUNT messages: consumer.commit(asynchronous=False)

    Error handling:
        - msg.error() is KafkaError._PARTITION_EOF -> log debug, continue
        - msg.error() is other -> raise KafkaException
        - json.JSONDecodeError -> log error, skip message, commit offset
        - redis.RedisError -> log error, skip message (do NOT commit — retry on restart)

    Shutdown:
        On _running=False (SIGTERM/SIGINT):
            consumer.commit(asynchronous=False)
            producer.flush(timeout=30.0)
            consumer.close()
    """
    global _running
    consumer.subscribe([config.KAFKA_INPUT_TOPIC])
    log.info("consumer_started", topic=config.KAFKA_INPUT_TOPIC, group=config.KAFKA_GROUP_ID)

    msg_count = 0
    try:
        while _running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    log.debug("partition_eof", partition=msg.partition())
                    continue
                raise KafkaException(msg.error())

            raw_value = msg.value()
            try:
                txn = json.loads(raw_value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.error(
                    "message_deserialize_error",
                    error=str(e),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )
                msg_count += 1
                if msg_count % config.KAFKA_MIN_COMMIT_COUNT == 0:
                    consumer.commit(asynchronous=False)
                continue

            user_id: str = txn["user_id"]

            try:
                prior_state = read_user_state(r, user_id)
                features = compute_and_write(r, txn, prior_state)
            except Exception as e:
                log.error(
                    "feature_compute_error",
                    user_id=user_id,
                    transaction_id=txn.get("transaction_id"),
                    error=str(e),
                )
                # Do NOT commit offset — allow retry on next startup
                continue

            # Build enriched message: original fields + all 14 features
            enriched = {**txn, **features}
            enriched_json = json.dumps(enriched).encode("utf-8")

            producer.produce(
                config.KAFKA_OUTPUT_TOPIC,
                value=enriched_json,
                key=user_id.encode("utf-8"),
                on_delivery=_delivery_callback,
            )
            producer.poll(0)

            msg_count += 1
            if msg_count % config.KAFKA_MIN_COMMIT_COUNT == 0:
                consumer.commit(asynchronous=False)

            log.debug(
                "message_processed",
                transaction_id=txn.get("transaction_id"),
                user_id=user_id,
                total_processed=msg_count,
            )

    finally:
        log.info("consumer_shutting_down", total_processed=msg_count)
        consumer.commit(asynchronous=False)
        producer.flush(timeout=30.0)
        consumer.close()
