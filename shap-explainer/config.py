"""
config.py — All environment variable parsing for shap-explainer service.
All other modules import from config, never from os.environ directly.
"""
import os

# --- PostgreSQL ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/frauddb",
)

# --- Model artifacts ---
MODEL_DIR              = os.environ.get("MODEL_DIR", "/app/models")
MODEL_TXT_PATH         = os.path.join(MODEL_DIR, "model.txt")
FEATURE_ORDER_PATH     = os.path.join(MODEL_DIR, "feature_order.json")

# --- Polling ---
SHAP_POLL_INTERVAL_SECONDS = int(os.environ.get("SHAP_POLL_INTERVAL_SECONDS", "5"))
SHAP_BATCH_SIZE            = int(os.environ.get("SHAP_BATCH_SIZE", "50"))

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
