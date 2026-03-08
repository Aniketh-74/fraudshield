"""
config.py — All environment variable parsing at module import time.
All other modules import from config, not from os.environ directly.
"""
import os

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "transactions")
KAFKA_RETRY_ATTEMPTS = int(os.environ.get("KAFKA_RETRY_ATTEMPTS", "12"))
KAFKA_RETRY_INTERVAL_SECONDS = int(os.environ.get("KAFKA_RETRY_INTERVAL_SECONDS", "5"))

# --- Rate / Fraud ---
TXN_RATE = float(os.environ.get("TXN_RATE", "10"))       # transactions per second
FRAUD_RATE = float(os.environ.get("FRAUD_RATE", "0.03"))  # 3% fraud injection rate

# --- Population ---
NUM_USERS = int(os.environ.get("NUM_USERS", "1000"))
NUM_MERCHANTS = int(os.environ.get("NUM_MERCHANTS", "200"))
_RANDOM_SEED_STR = os.environ.get("RANDOM_SEED", "")
RANDOM_SEED = int(_RANDOM_SEED_STR) if _RANDOM_SEED_STR else None

# --- CSV Output ---
DATA_OUTPUT_PATH = os.environ.get("DATA_OUTPUT_PATH", "./data/transactions.csv")
CSV_FLUSH_INTERVAL = int(os.environ.get("CSV_FLUSH_INTERVAL", "100"))
OVERWRITE_CSV = os.environ.get("OVERWRITE_CSV", "false").lower() == "true"

# --- Fraud Pattern Thresholds ---
RAPID_FIRE_WINDOW_SECONDS = int(os.environ.get("RAPID_FIRE_WINDOW_SECONDS", "60"))
RAPID_FIRE_MIN_TXNS = int(os.environ.get("RAPID_FIRE_MIN_TXNS", "3"))
AMOUNT_SPIKE_MULTIPLIER = float(os.environ.get("AMOUNT_SPIKE_MULTIPLIER", "10"))
GEO_VELOCITY_WINDOW_MINUTES = int(os.environ.get("GEO_VELOCITY_WINDOW_MINUTES", "10"))
GEO_VELOCITY_MAX_KMH = float(os.environ.get("GEO_VELOCITY_MAX_KMH", "900"))
MIDNIGHT_LARGE_START_HOUR = int(os.environ.get("MIDNIGHT_LARGE_START_HOUR", "1"))
MIDNIGHT_LARGE_END_HOUR = int(os.environ.get("MIDNIGHT_LARGE_END_HOUR", "5"))
MIDNIGHT_LARGE_MIN_AMOUNT = float(os.environ.get("MIDNIGHT_LARGE_MIN_AMOUNT", "10000"))
UNUSUAL_MERCHANT_MIN_AMOUNT = float(os.environ.get("UNUSUAL_MERCHANT_MIN_AMOUNT", "50000"))

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
