"""
predictor.py — Core inference logic.

Functions:
    classify_risk(probability: float) -> str
    predict(calibrated_model, feature_order: list, feature_values: dict) -> tuple[float, str]

Risk thresholds (from config, aligned with SCORE-05):
    LOW    <  0.3
    MEDIUM >= 0.3 and <= 0.7
    HIGH   >  0.7
"""
import time

import numpy as np

import config
from metrics import PREDICTION_LATENCY, PREDICTIONS_TOTAL


def classify_risk(probability: float) -> str:
    """
    Map fraud probability to risk level string.

    Thresholds (from SCORE-05 — locked):
        LOW    : probability < RISK_LOW_THRESHOLD  (default 0.3)
        MEDIUM : RISK_LOW_THRESHOLD <= probability <= RISK_HIGH_THRESHOLD
        HIGH   : probability > RISK_HIGH_THRESHOLD (default 0.7)
    """
    if probability < config.RISK_LOW_THRESHOLD:
        return "LOW"
    elif probability <= config.RISK_HIGH_THRESHOLD:
        return "MEDIUM"
    else:
        return "HIGH"


def predict(
    calibrated_model,
    feature_order: list,
    feature_values: dict,
) -> tuple:
    """
    Run a single fraud prediction.

    Args:
        calibrated_model: CalibratedClassifierCV loaded by model_loader.
        feature_order:    List of 14 feature name strings in exact order from feature_order.json.
        feature_values:   Dict mapping feature name → float value (from PredictRequest).

    Returns:
        (fraud_probability, risk_level)
        fraud_probability: float in [0, 1]
        risk_level: "LOW" | "MEDIUM" | "HIGH"

    Feature ordering enforcement:
        X = np.array([[feature_values[f] for f in feature_order]], dtype=np.float64)
        This iterates feature_order (the JSON list), NOT the dict, guaranteeing correct order.
        Dict key order is irrelevant — the feature_order list determines position.

    Latency measurement:
        Uses time.perf_counter() (monotonic, nanosecond resolution).
        Elapsed time includes only predict_proba(); not JSON serialization.
        Result observed into PREDICTION_LATENCY histogram.
    """
    # Build (1, 14) numpy array in exact feature order
    X = np.array(
        [[feature_values[f] for f in feature_order]],
        dtype=np.float64,
    )

    start = time.perf_counter()
    proba_array = calibrated_model.predict_proba(X)
    elapsed = time.perf_counter() - start

    # Index 1 = positive class (fraud). Shape: (1, 2) → scalar
    fraud_probability: float = float(proba_array[0, 1])
    risk_level: str = classify_risk(fraud_probability)

    # Record Prometheus metrics
    PREDICTION_LATENCY.observe(elapsed)
    PREDICTIONS_TOTAL.labels(risk_level=risk_level).inc()

    return fraud_probability, risk_level
