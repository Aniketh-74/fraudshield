"""
config.py — All environment variable parsing for feature-enrichment service.
All other modules import from config, never from os.environ directly.
"""
import os

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_INPUT_TOPIC = os.environ.get("KAFKA_INPUT_TOPIC", "transactions")
KAFKA_OUTPUT_TOPIC = os.environ.get("KAFKA_OUTPUT_TOPIC", "enriched-transactions")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "feature-enrichment-group")
KAFKA_RETRY_ATTEMPTS = int(os.environ.get("KAFKA_RETRY_ATTEMPTS", "12"))
KAFKA_RETRY_INTERVAL_SECONDS = int(os.environ.get("KAFKA_RETRY_INTERVAL_SECONDS", "5"))
KAFKA_MIN_COMMIT_COUNT = int(os.environ.get("KAFKA_MIN_COMMIT_COUNT", "10"))

# --- Redis ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
REDIS_RETRY_ATTEMPTS = int(os.environ.get("REDIS_RETRY_ATTEMPTS", "3"))
REDIS_RETRY_BACKOFF_SECONDS = float(os.environ.get("REDIS_RETRY_BACKOFF_SECONDS", "1.0"))

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
