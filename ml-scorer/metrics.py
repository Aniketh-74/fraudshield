"""
metrics.py — Module-level Prometheus metric definitions.

All metrics are singletons registered at import time.
Import from this module — do NOT instantiate metrics elsewhere.

Metrics exposed:
    PREDICTION_LATENCY  — Histogram, prediction_latency_seconds
    PREDICTIONS_TOTAL   — Counter,   predictions_total{risk_level}
    MODEL_VERSION_INFO  — Gauge,     model_version_info{version}
"""
from prometheus_client import Histogram, Counter, Gauge

# prediction_latency_seconds — Histogram
# Buckets: [.005, .01, .025, .05, .075, .1, .25, .5] seconds
# (.05 = 50ms SLA boundary; allows histogram_quantile(0.99) to resolve sub-50ms)
PREDICTION_LATENCY = Histogram(
    "prediction_latency_seconds",
    "Time in seconds for a single fraud probability prediction",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5],
)

# predictions_total — Counter with risk_level label
# Labels: risk_level in {"LOW", "MEDIUM", "HIGH"}
# IMPORTANT: bounded labels only (no user_id, transaction_id — violates MON-03)
PREDICTIONS_TOTAL = Counter(
    "predictions_total",
    "Total number of fraud predictions served",
    ["risk_level"],
)

# model_version_info — Gauge set to 1.0 for the currently loaded version
# Usage: MODEL_VERSION_INFO.labels(version="v1").set(1)
MODEL_VERSION_INFO = Gauge(
    "model_version_info",
    "Information about the currently loaded model version",
    ["version"],
)
