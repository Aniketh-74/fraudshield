#!/bin/bash
# init-topics.sh — Create Kafka topics required by the fraud detection pipeline.
# Usage: ./init-topics.sh [bootstrap-server]
# Default bootstrap server: kafka:9092 (for Docker Compose network)

set -e

BOOTSTRAP="${1:-kafka:9092}"

echo "Creating Kafka topics on ${BOOTSTRAP}..."

kafka-topics --bootstrap-server "${BOOTSTRAP}" \
    --create --if-not-exists \
    --topic transactions \
    --partitions 6 \
    --replication-factor 1

kafka-topics --bootstrap-server "${BOOTSTRAP}" \
    --create --if-not-exists \
    --topic enriched-transactions \
    --partitions 6 \
    --replication-factor 1

kafka-topics --bootstrap-server "${BOOTSTRAP}" \
    --create --if-not-exists \
    --topic decisions \
    --partitions 6 \
    --replication-factor 1

echo "Topics created. Listing all topics:"
kafka-topics --bootstrap-server "${BOOTSTRAP}" --list
