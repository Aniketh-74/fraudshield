"""
TEST-04: ML scorer latency integration test.

Requires ml-scorer to be running. Skipped automatically when service is not available.
Run with: docker compose up ml-scorer -d
"""
import time

import httpx
import pytest

SCORER_URL = "http://localhost:8000"


def _is_scorer_running():
    """Must be defined BEFORE the skipif decorator that calls it."""
    try:
        httpx.get(f"{SCORER_URL}/health", timeout=1.0)
        return True
    except Exception:
        return False


SCORER_AVAILABLE = _is_scorer_running()

PREDICT_PAYLOAD = {
    "transaction_id": "test-latency-001",
    "user_id": "u001",
    "amount": 1000.0,
    "merchant_category": "groceries",
    "txn_count_1h": 2,
    "txn_count_6h": 5,
    "txn_count_24h": 10,
    "avg_amount_7d": 800.0,
    "amount_deviation": 0.25,
    "time_since_last_txn_seconds": 3600.0,
    "unique_merchants_24h": 3,
    "max_amount_24h": 1200.0,
    "is_new_merchant": 0,
    "hour_of_day": 14,
    "is_weekend": 0,
    "geo_distance_km": 0.0,
    "geo_velocity_kmh": 0.0,
    "merchant_category_enc": 0,
}


@pytest.mark.skipif(not SCORER_AVAILABLE, reason="ml-scorer not running — start with: docker compose up ml-scorer -d")
def test_ml_scorer_responds_within_50ms():
    """TEST-04: ML scorer /predict must respond within 50ms SLA."""
    start = time.perf_counter()
    response = httpx.post(f"{SCORER_URL}/predict", json=PREDICT_PAYLOAD, timeout=2.0)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert elapsed_ms < 50, f"p99 latency {elapsed_ms:.1f}ms exceeds 50ms SLA"

    data = response.json()
    assert "fraud_probability" in data
    assert 0.0 <= data["fraud_probability"] <= 1.0


@pytest.mark.skipif(not SCORER_AVAILABLE, reason="ml-scorer not running — start with: docker compose up ml-scorer -d")
def test_ml_scorer_returns_valid_risk_level():
    """Risk level must be LOW, MEDIUM, or HIGH."""
    response = httpx.post(f"{SCORER_URL}/predict", json=PREDICT_PAYLOAD, timeout=2.0)
    assert response.status_code == 200

    data = response.json()
    assert "risk_level" in data
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH"), f"Unexpected risk_level: {data['risk_level']}"


@pytest.mark.skipif(not SCORER_AVAILABLE, reason="ml-scorer not running — start with: docker compose up ml-scorer -d")
def test_ml_scorer_p50_latency_under_load():
    """Run 20 sequential predictions and verify median latency < 30ms."""
    latencies = []
    for _ in range(20):
        start = time.perf_counter()
        response = httpx.post(f"{SCORER_URL}/predict", json=PREDICT_PAYLOAD, timeout=2.0)
        latencies.append((time.perf_counter() - start) * 1000)
        assert response.status_code == 200

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p99 = latencies[-1]
    print(f"\n  p50={p50:.1f}ms  p99={p99:.1f}ms  (20 sequential requests)")
    assert p50 < 30, f"p50 {p50:.1f}ms exceeds 30ms target"
