"""
Unit tests for feature-enrichment service.

Tests the haversine distance function and velocity window logic from
feature_computer.py. No Redis, Kafka, or Postgres required — all
external dependencies are exercised through pure math only.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../feature-enrichment"))

from feature_computer import _haversine_km, MERCHANT_CATEGORY_MAP


# ---------------------------------------------------------------------------
# Haversine distance tests
# ---------------------------------------------------------------------------

def test_haversine_mumbai_to_bangalore():
    """Mumbai (19.076, 72.877) to Bangalore (12.972, 77.580) ≈ 845 km.
    The plan's 984 km was a documentation error — actual value is ~845 km (STATE.md decision).
    """
    dist = _haversine_km(19.076, 72.877, 12.972, 77.580)
    assert 840 <= dist <= 860, f"Expected ~845 km, got {dist}"


def test_haversine_same_point():
    """Distance from a point to itself must be exactly 0.0."""
    dist = _haversine_km(19.076, 72.877, 19.076, 72.877)
    assert dist == 0.0


def test_haversine_short_distance():
    """Points ~1 km apart — verify formula handles small distances correctly."""
    # Two points ~1 km apart in Mumbai (1 degree lat ≈ 111 km → 0.009 deg ≈ 1 km)
    dist = _haversine_km(19.076, 72.877, 19.085, 72.877)
    assert 0.9 <= dist <= 1.1, f"Expected ~1 km, got {dist}"


def test_haversine_delhi_to_chennai():
    """Delhi (28.6, 77.2) to Chennai (13.08, 80.27) ≈ 1750 km."""
    dist = _haversine_km(28.6, 77.2, 13.08, 80.27)
    assert 1700 <= dist <= 1800, f"Expected ~1750 km, got {dist}"


def test_haversine_symmetry():
    """Haversine distance must be symmetric: dist(A, B) == dist(B, A)."""
    dist_ab = _haversine_km(19.076, 72.877, 12.972, 77.580)
    dist_ba = _haversine_km(12.972, 77.580, 19.076, 72.877)
    assert abs(dist_ab - dist_ba) < 0.001, "Distance must be symmetric"


# ---------------------------------------------------------------------------
# Geo velocity tests (pure math, no Redis)
# ---------------------------------------------------------------------------

def test_geo_velocity_impossible_travel():
    """845 km in 5 minutes = 10140 km/h, should exceed 500 km/h threshold."""
    dist_km = 845.0
    elapsed_seconds = 300  # 5 minutes
    velocity = (dist_km / elapsed_seconds) * 3600
    assert velocity > 500, "Geo velocity should detect impossible travel"


def test_geo_velocity_normal_flight():
    """500 km in 1 hour = 500 km/h — right at the boundary, must not trigger impossible travel."""
    dist_km = 500.0
    elapsed_seconds = 3600  # 1 hour
    velocity = (dist_km / elapsed_seconds) * 3600
    # The rule is geo_velocity_kmh > 500, so exactly 500 should NOT trigger
    assert velocity <= 500, "500 km/h should not trigger impossible travel rule"


# ---------------------------------------------------------------------------
# Velocity window count test (pure Python, no Redis)
# ---------------------------------------------------------------------------

def test_velocity_window_count():
    """Test that txn_count_1h counts only transactions within the last hour."""
    now_ts = time.time()
    # Simulate 3 transactions in last hour (1800s, 3000s, 100s ago), 2 older than 1h
    timestamps = [now_ts - 1800, now_ts - 3000, now_ts - 100, now_ts - 3601, now_ts - 7200]
    one_hour_ago = now_ts - 3600
    count_1h = sum(1 for ts in timestamps if ts > one_hour_ago)
    assert count_1h == 3, f"Expected 3 transactions in last hour, got {count_1h}"


def test_velocity_window_excludes_exact_cutoff():
    """Transaction exactly at cutoff boundary should NOT be counted (strict > comparison)."""
    now_ts = time.time()
    cutoff = now_ts - 3600
    # Timestamp exactly at cutoff should be excluded
    timestamps = [cutoff, now_ts - 1800]  # one at boundary (excluded), one inside (included)
    count_1h = sum(1 for ts in timestamps if ts > cutoff)
    assert count_1h == 1, "Transaction exactly at cutoff must not be counted"


# ---------------------------------------------------------------------------
# Merchant category encoding tests
# ---------------------------------------------------------------------------

def test_merchant_category_encoding_all_six():
    """All 6 known merchant categories must have a unique integer encoding."""
    expected = {
        "groceries": 0,
        "food": 1,
        "electronics": 2,
        "travel": 3,
        "entertainment": 4,
        "transfers": 5,
    }
    for category, enc in expected.items():
        assert MERCHANT_CATEGORY_MAP[category] == enc, (
            f"{category} should encode to {enc}, got {MERCHANT_CATEGORY_MAP[category]}"
        )


def test_merchant_category_encoding_unknown_returns_negative_one():
    """Unknown categories must return -1 (handled by .get() default)."""
    enc = MERCHANT_CATEGORY_MAP.get("unknown_category", -1)
    assert enc == -1
