"""
kafka_producer.py — Kafka producer wrapper using confluent-kafka (librdkafka-based).

Functions:
  build_producer      — Create a production-grade confluent Producer
  delivery_callback   — Delivery report handler for async callbacks
  produce_transaction — Produce one transaction dict to Kafka
  flush_producer      — Block until all queued messages are delivered
  wait_for_kafka      — Startup retry loop; exits non-zero on exhaustion
"""
import json
import sys
import time

from confluent_kafka import Producer, KafkaException
import structlog

logger = structlog.get_logger(__name__)


def build_producer(bootstrap_servers: str) -> Producer:
    """Create a production-grade Kafka Producer with tuned settings."""
    return Producer({
        "bootstrap.servers": bootstrap_servers,
        "acks": "all",                            # Wait for all ISR replicas — durability
        "linger.ms": 5,                           # Batch for 5ms — low latency at 10 TPS
        "compression.type": "lz4",               # Fast compression, good ratio
        "batch.size": 65536,                      # 64 KB batch size
        "queue.buffering.max.messages": 100000,
        "delivery.report.only.error": False,      # Report all deliveries
    })


def delivery_callback(err, msg) -> None:
    """Delivery report callback — called by librdkafka for each produced message."""
    if err:
        logger.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        logger.debug(
            "kafka_delivered",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


def produce_transaction(producer: Producer, topic: str, txn_dict: dict) -> None:
    """Produce one transaction (without is_fraud) to Kafka.

    Args:
        producer: confluent Producer instance
        topic:    Kafka topic name
        txn_dict: transaction dict from Transaction.to_kafka_dict() — must NOT contain is_fraud
    """
    producer.produce(
        topic,
        value=json.dumps(txn_dict).encode("utf-8"),
        key=txn_dict["user_id"].encode("utf-8"),   # Partition by user_id for ordering
        on_delivery=delivery_callback,
    )
    producer.poll(0)  # Trigger callbacks without blocking


def flush_producer(producer: Producer, timeout: float = 30.0) -> None:
    """Block until all queued messages are delivered or timeout expires."""
    remaining = producer.flush(timeout=timeout)
    if remaining > 0:
        logger.warning("kafka_flush_incomplete", remaining_messages=remaining)


def wait_for_kafka(
    bootstrap_servers: str, max_attempts: int, interval_seconds: int
) -> Producer:
    """
    Verify Kafka connectivity before starting the main loop.

    Creates a Producer and calls list_topics() as a live-broker probe.
    Retries up to max_attempts times with interval_seconds between attempts.
    On success, returns a fully-configured production Producer.
    On exhaustion, calls sys.exit(1) so Kubernetes can restart the pod.

    Note: confluent-kafka Producer constructor does NOT connect immediately;
    list_topics() forces the actual broker connection attempt (Pitfall 4).
    """
    for attempt in range(1, max_attempts + 1):
        try:
            # Use a minimal probe producer — replaced by full production producer on success
            probe = Producer({"bootstrap.servers": bootstrap_servers})
            probe.list_topics(timeout=5)
            logger.info("kafka_connected", attempt=attempt, bootstrap_servers=bootstrap_servers)
            # Return a full production producer now that we know broker is up
            return build_producer(bootstrap_servers)
        except KafkaException as e:
            logger.warning(
                "kafka_unavailable",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e),
            )
            if attempt < max_attempts:
                time.sleep(interval_seconds)

    logger.error("kafka_connection_exhausted", max_attempts=max_attempts)
    sys.exit(1)
