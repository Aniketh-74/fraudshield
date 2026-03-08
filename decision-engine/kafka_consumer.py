"""
kafka_consumer.py — Confluent Kafka consumer + producer for decision engine.

Follows feature-enrichment/kafka_consumer.py pattern exactly.

Functions:
    build_consumer          — Consumer with decision-engine-group settings
    build_output_producer   — Producer for decisions topic
    wait_for_kafka_consumer — Startup probe with retry loop
    apply_decision_matrix   — Pure function: risk_level + fired_rules -> decision
    run_consumer_loop       — Main poll loop: consume -> score -> rules -> decide -> store -> publish
"""
import json
import signal
import sys
import time

import structlog
from confluent_kafka import Consumer, Producer, KafkaException, KafkaError

import config
from rules_engine import RulesEngine
from scorer_client import ScorerClient
from db_writer import DBWriter
from ws_broadcaster import WSBroadcaster

log = structlog.get_logger(__name__)

_running = True


def _signal_handler(sig, frame) -> None:
    global _running
    log.info("shutdown_signal_received", signal=sig)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def build_consumer() -> Consumer:
    """
    Consumer config matches feature-enrichment pattern.
    group.id: config.KAFKA_GROUP_ID ("decision-engine-group")
    Manual commit; max.poll.interval.ms 300000 — adequate for HTTP + DB latency.
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
    """Producer config identical to feature-enrichment/kafka_consumer.py."""
    return Producer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",
        "linger.ms": 5,
        "compression.type": "none",
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
    Mirrors feature-enrichment/kafka_consumer.py wait_for_kafka_consumer() exactly.
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


def apply_decision_matrix(risk_level: str, fired_rules: list[str]) -> str:
    """
    Decision matrix (locked in CONTEXT.md DECN-03):
        HIGH  + any rule fired -> BLOCK
        HIGH  + no rule fired  -> FLAG
        MEDIUM + any rule fired -> FLAG
        MEDIUM + no rule fired  -> APPROVE
        LOW  (any)             -> APPROVE
    """
    if risk_level == "HIGH":
        return "BLOCK" if fired_rules else "FLAG"
    elif risk_level == "MEDIUM":
        return "FLAG" if fired_rules else "APPROVE"
    else:  # LOW
        return "APPROVE"


def run_consumer_loop(
    consumer: Consumer,
    producer: Producer,
    rules_engine: RulesEngine,
    scorer_client: ScorerClient,
    db_writer: DBWriter,
    ws_broadcaster: WSBroadcaster,
) -> None:
    """
    Main consumer poll loop.

    Per-message flow:
        1. consumer.poll(timeout=1.0)
        2. json.loads -> enriched_txn dict
        3. Inject is_international=0.0 (not in Phase 3 enrichment output)
        4. scorer_client.predict(enriched_txn) -> score dict
        5. If _fallback: APPROVE, skip DB, still publish + broadcast, commit, continue
        6. rules_engine.evaluate(features) -> fired_rules list
        7. apply_decision_matrix(risk_level, fired_rules) -> decision
        8. If FLAG or BLOCK: db_writer.write_decision(...)  [non-blocking]
        9. producer.produce(decisions topic, output_msg)
        10. ws_broadcaster.broadcast(ws_msg)
        11. Commit every KAFKA_MIN_COMMIT_COUNT messages

    Error handling mirrors feature-enrichment/kafka_consumer.py:
        - KafkaError._PARTITION_EOF   -> debug log, continue
        - Other KafkaError             -> raise KafkaException
        - json.JSONDecodeError         -> log error, skip + commit
        - Scorer failure               -> fail-open (APPROVE), log warning
        - DB failure                   -> non-blocking, logged inside db_writer
    """
    from datetime import datetime, timezone

    global _running
    consumer.subscribe([config.KAFKA_INPUT_TOPIC])
    log.info(
        "consumer_started",
        input_topic=config.KAFKA_INPUT_TOPIC,
        output_topic=config.KAFKA_OUTPUT_TOPIC,
        group=config.KAFKA_GROUP_ID,
    )

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

            try:
                enriched_txn = json.loads(msg.value().decode("utf-8"))
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

            txn_id = enriched_txn.get("transaction_id", "")
            user_id = enriched_txn.get("user_id", "")
            amount = float(enriched_txn.get("amount", 0.0))

            # Extract location fields (added in Phase 5 schema)
            location = enriched_txn.get("location", {})
            location_lat = float(location.get("lat", 0.0)) if location else None
            location_lng = float(location.get("lng", 0.0)) if location else None

            # Compute processing latency from Kafka message timestamp
            msg_ts_ms = msg.timestamp()[1]  # epoch ms from Kafka message timestamp
            now_ms = time.time() * 1000
            processing_latency_ms = round(now_ms - msg_ts_ms, 2) if msg_ts_ms > 0 else None

            # Inject is_international default (Phase 3 enrichment does not compute this)
            features = {**enriched_txn, "is_international": float(enriched_txn.get("is_international", 0.0))}

            # Step 1: Call ML scorer (fail-open on any error)
            score = scorer_client.predict(features)
            is_fallback = score.get("_fallback", False)

            if is_fallback:
                decision = "APPROVE"
                fired_rules: list[str] = []
                fraud_probability = 0.0
                risk_level = "LOW"
                log.warning("scorer_fallback_approve", transaction_id=txn_id)
            else:
                fraud_probability = float(score["fraud_probability"])
                risk_level = score["risk_level"]

                # Step 2: Evaluate business rules
                fired_rules = rules_engine.evaluate(features)

                # Step 3: Apply decision matrix
                decision = apply_decision_matrix(risk_level, fired_rules)

            # Step 4: Store to PostgreSQL (all decisions), non-blocking
            # Build clean feature_vector: only the 14 model features
            feature_vector = {
                k: float(features.get(k, 0.0))
                for k in [
                    "txn_count_1h", "txn_count_6h", "txn_count_24h",
                    "avg_amount_7d", "amount_deviation", "time_since_last_txn_seconds",
                    "unique_merchants_24h", "max_amount_24h", "is_new_merchant",
                    "hour_of_day", "is_weekend", "geo_distance_km",
                    "geo_velocity_kmh", "merchant_category_enc",
                ]
            }
            db_writer.write_decision(
                txn_id=txn_id,
                user_id=user_id,
                amount=amount,
                fraud_probability=fraud_probability,
                risk_level=risk_level,
                decision=decision,
                fired_rules=fired_rules,
                feature_vector=feature_vector,
                location_lat=location_lat,
                location_lng=location_lng,
                processing_latency_ms=processing_latency_ms,
            )

            # Step 5: Publish to Kafka decisions topic (all decisions)
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            output_msg = {
                "transaction_id": txn_id,
                "user_id": user_id,
                "amount": amount,
                "fraud_probability": fraud_probability,
                "risk_level": risk_level,
                "decision": decision,
                "fired_rules": fired_rules,
                "timestamp": timestamp_iso,
            }
            producer.produce(
                config.KAFKA_OUTPUT_TOPIC,
                value=json.dumps(output_msg).encode("utf-8"),
                key=user_id.encode("utf-8"),
                on_delivery=_delivery_callback,
            )
            producer.poll(0)

            # Step 6: Broadcast via WebSocket (all decisions)
            ws_broadcaster.broadcast(output_msg)

            msg_count += 1
            if msg_count % config.KAFKA_MIN_COMMIT_COUNT == 0:
                consumer.commit(asynchronous=False)

            log.info(
                "decision_made",
                transaction_id=txn_id,
                decision=decision,
                risk_level=risk_level,
                fraud_probability=round(fraud_probability, 4),
                fired_rules=fired_rules,
                fallback=is_fallback,
            )

    finally:
        log.info("consumer_shutting_down", total_processed=msg_count)
        consumer.commit(asynchronous=False)
        producer.flush(timeout=30.0)
        consumer.close()
