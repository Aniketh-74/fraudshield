"""
Unit tests for ml-scorer service.

Tests the classify_risk function and predict function logic.
The model is mocked so no model files (calibrated_model.pkl, feature_order.json)
are required for unit tests.

All tests pass without any running infrastructure.
"""
import sys
import os
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

_ML_SCORER_PATH = os.path.join(os.path.dirname(__file__), "../../ml-scorer")

# Ensure ml-scorer is first in path (before any decision-engine path)
if _ML_SCORER_PATH in sys.path:
    sys.path.remove(_ML_SCORER_PATH)
sys.path.insert(0, _ML_SCORER_PATH)


@pytest.fixture(autouse=True)
def reset_ml_scorer_modules():
    """
    Purge and reload ml-scorer's config/metrics/predictor before each test.

    Multiple services share the module name 'config'. Without this fixture,
    the decision-engine's config.py (which lacks RISK_LOW_THRESHOLD) would
    shadow ml-scorer's config.py after pytest collects all test files.
    """
    # Remove stale modules from other services
    for mod in list(sys.modules.keys()):
        if mod in ("config", "metrics", "predictor"):
            del sys.modules[mod]

    # Guarantee ml-scorer path is first
    if _ML_SCORER_PATH in sys.path:
        sys.path.remove(_ML_SCORER_PATH)
    sys.path.insert(0, _ML_SCORER_PATH)

    yield

    # Cleanup after test so other test modules get a clean state too
    for mod in list(sys.modules.keys()):
        if mod in ("config", "metrics", "predictor"):
            del sys.modules[mod]


# ---------------------------------------------------------------------------
# classify_risk tests — pure function, no mocking needed
# ---------------------------------------------------------------------------

def test_classify_risk_low():
    """Probability < 0.3 must return 'LOW'."""
    from predictor import classify_risk
    assert classify_risk(0.0) == "LOW"
    assert classify_risk(0.1) == "LOW"
    assert classify_risk(0.29) == "LOW"


def test_classify_risk_medium():
    """Probability in [0.3, 0.7] must return 'MEDIUM'."""
    from predictor import classify_risk
    assert classify_risk(0.3) == "MEDIUM"
    assert classify_risk(0.5) == "MEDIUM"
    assert classify_risk(0.7) == "MEDIUM"


def test_classify_risk_high():
    """Probability > 0.7 must return 'HIGH'."""
    from predictor import classify_risk
    assert classify_risk(0.71) == "HIGH"
    assert classify_risk(0.8) == "HIGH"
    assert classify_risk(1.0) == "HIGH"


def test_classify_risk_thresholds():
    """Verify exact boundary values match SCORE-05 spec: LOW < 0.3, MEDIUM 0.3-0.7, HIGH > 0.7."""
    from predictor import classify_risk
    cases = [
        (0.1, "LOW"),
        (0.5, "MEDIUM"),
        (0.8, "HIGH"),
    ]
    for prob, expected_level in cases:
        actual = classify_risk(prob)
        assert actual == expected_level, (
            f"classify_risk({prob}) = {actual!r}, expected {expected_level!r}"
        )


# ---------------------------------------------------------------------------
# predict function tests — mock the model
# ---------------------------------------------------------------------------

def _make_mock_model(fraud_probability: float):
    """Create a mock calibrated model that returns a fixed fraud probability.

    predict_proba must return a numpy array of shape (1, 2) because predictor.py
    uses numpy indexing: proba_array[0, 1] (tuple-indexing, not list-indexing).
    """
    mock_model = MagicMock()
    legit_prob = 1.0 - fraud_probability
    # Shape (1, 2): [[legit_prob, fraud_prob]]
    mock_model.predict_proba.return_value = np.array([[legit_prob, fraud_probability]])
    return mock_model


_FEATURE_ORDER = [
    "txn_count_1h", "txn_count_6h", "txn_count_24h",
    "avg_amount_7d", "amount_deviation", "time_since_last_txn_seconds",
    "unique_merchants_24h", "max_amount_24h", "is_new_merchant",
    "hour_of_day", "is_weekend", "geo_distance_km",
    "geo_velocity_kmh", "merchant_category_enc",
]

_SAMPLE_FEATURES = {f: 0.0 for f in _FEATURE_ORDER}


def test_predict_returns_fraud_probability_in_range():
    """Prediction result fraud_probability must be in [0.0, 1.0]."""
    from predictor import predict
    with patch("predictor.PREDICTION_LATENCY") as mock_lat, \
         patch("predictor.PREDICTIONS_TOTAL") as mock_total:
        mock_lat.observe = MagicMock()
        mock_total.labels.return_value.inc = MagicMock()

        mock_model = _make_mock_model(0.65)
        fraud_prob, risk_level = predict(mock_model, _FEATURE_ORDER, _SAMPLE_FEATURES)

        assert 0.0 <= fraud_prob <= 1.0, f"fraud_probability {fraud_prob} not in [0, 1]"


def test_predict_low_probability_returns_low_risk():
    """Model output 0.1 → LOW risk level."""
    from predictor import predict
    with patch("predictor.PREDICTION_LATENCY") as mock_lat, \
         patch("predictor.PREDICTIONS_TOTAL") as mock_total:
        mock_lat.observe = MagicMock()
        mock_total.labels.return_value.inc = MagicMock()

        mock_model = _make_mock_model(0.1)
        fraud_prob, risk_level = predict(mock_model, _FEATURE_ORDER, _SAMPLE_FEATURES)

        assert risk_level == "LOW", f"Expected LOW, got {risk_level}"
        assert abs(fraud_prob - 0.1) < 0.001


def test_predict_medium_probability_returns_medium_risk():
    """Model output 0.5 → MEDIUM risk level."""
    from predictor import predict
    with patch("predictor.PREDICTION_LATENCY") as mock_lat, \
         patch("predictor.PREDICTIONS_TOTAL") as mock_total:
        mock_lat.observe = MagicMock()
        mock_total.labels.return_value.inc = MagicMock()

        mock_model = _make_mock_model(0.5)
        fraud_prob, risk_level = predict(mock_model, _FEATURE_ORDER, _SAMPLE_FEATURES)

        assert risk_level == "MEDIUM", f"Expected MEDIUM, got {risk_level}"


def test_predict_high_probability_returns_high_risk():
    """Model output 0.9 → HIGH risk level."""
    from predictor import predict
    with patch("predictor.PREDICTION_LATENCY") as mock_lat, \
         patch("predictor.PREDICTIONS_TOTAL") as mock_total:
        mock_lat.observe = MagicMock()
        mock_total.labels.return_value.inc = MagicMock()

        mock_model = _make_mock_model(0.9)
        fraud_prob, risk_level = predict(mock_model, _FEATURE_ORDER, _SAMPLE_FEATURES)

        assert risk_level == "HIGH", f"Expected HIGH, got {risk_level}"


def test_predict_enforces_feature_order():
    """Features must be ordered per feature_order list — model receives features in exact order."""
    from predictor import predict

    observed_X = []

    def capture_predict_proba(X):
        observed_X.append(X.tolist())
        return np.array([[0.9, 0.1]])

    with patch("predictor.PREDICTION_LATENCY") as mock_lat, \
         patch("predictor.PREDICTIONS_TOTAL") as mock_total:
        mock_lat.observe = MagicMock()
        mock_total.labels.return_value.inc = MagicMock()

        mock_model = MagicMock()
        mock_model.predict_proba.side_effect = capture_predict_proba

        # Set distinct values for each feature so order matters
        feature_values = {f: float(i) for i, f in enumerate(_FEATURE_ORDER)}

        predict(mock_model, _FEATURE_ORDER, feature_values)

    # The array passed to predict_proba must match the order of _FEATURE_ORDER
    assert len(observed_X) == 1
    row = observed_X[0][0]
    expected_row = [float(i) for i in range(len(_FEATURE_ORDER))]
    assert row == expected_row, f"Feature order mismatch.\nExpected: {expected_row}\nGot: {row}"
