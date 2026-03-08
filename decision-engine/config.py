"""
config.py — All environment variable parsing for decision-engine service.
All other modules import from config, never from os.environ directly.
"""
import os

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS     = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_INPUT_TOPIC           = os.environ.get("KAFKA_INPUT_TOPIC", "enriched-transactions")
KAFKA_OUTPUT_TOPIC          = os.environ.get("KAFKA_OUTPUT_TOPIC", "decisions")
KAFKA_GROUP_ID              = os.environ.get("KAFKA_GROUP_ID", "decision-engine-group")
KAFKA_RETRY_ATTEMPTS        = int(os.environ.get("KAFKA_RETRY_ATTEMPTS", "12"))
KAFKA_RETRY_INTERVAL_SECONDS = int(os.environ.get("KAFKA_RETRY_INTERVAL_SECONDS", "5"))
KAFKA_MIN_COMMIT_COUNT      = int(os.environ.get("KAFKA_MIN_COMMIT_COUNT", "5"))

# --- ML Scorer ---
SCORER_URL = os.environ.get("SCORER_URL", "http://localhost:8000")

# --- PostgreSQL ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/frauddb")

# --- Rules ---
RULES_CONFIG_PATH = os.environ.get("RULES_CONFIG_PATH", "/app/rules.yaml")

# --- WebSocket ---
WS_HOST = os.environ.get("WS_HOST", "0.0.0.0")
WS_PORT = int(os.environ.get("WS_PORT", "8765"))

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
