"""
config.py — All environment variable parsing for ml-scorer service.
All other modules import from config, never from os.environ directly.
"""
import os

# --- Model ---
MODEL_DIR = os.environ.get("MODEL_DIR", "/app/models")
# calibrated_model.pkl path: {MODEL_DIR}/calibrated_model.pkl
# feature_order.json path:   {MODEL_DIR}/feature_order.json
# model_version.txt path:    {MODEL_DIR}/model_version.txt  (optional)

# --- Server ---
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
WORKERS = int(os.environ.get("WORKERS", "1"))  # Single worker: model is not fork-safe

# --- Risk Thresholds (locked from CONTEXT.md / SCORE-05) ---
RISK_LOW_THRESHOLD = float(os.environ.get("RISK_LOW_THRESHOLD", "0.3"))   # < 0.3 = LOW
RISK_HIGH_THRESHOLD = float(os.environ.get("RISK_HIGH_THRESHOLD", "0.7"))  # > 0.7 = HIGH
# MEDIUM is 0.3 <= p <= 0.7

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
