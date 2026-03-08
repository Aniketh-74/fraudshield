"""
TEST-03: Integration test — Redis velocity feature updates.

Verifies that sorted-set based velocity counting works correctly with a real
testcontainers Redis instance. Exercises the same Redis data structures that
feature-enrichment uses in production.
"""
import time

import pytest
import redis as redis_lib


def test_five_rapid_transactions_update_velocity_count(redis_container):
    """TEST-03: 5 transactions within 1 hour are counted correctly in Redis sorted set."""
    r = redis_lib.Redis.from_url(redis_container.get_connection_url())
    user_id = "velocity_test_user"
    now = time.time()

    for i in range(5):
        r.zadd(f"user:{user_id}:txn_ts", {f"txn_{i}": now - (i * 10)})

    one_hour_ago = now - 3600
    count = r.zcount(f"user:{user_id}:txn_ts", one_hour_ago, "+inf")
    assert count == 5, f"Expected 5 velocity transactions in last hour, found {count}"


def test_old_transactions_excluded_from_velocity_window(redis_container):
    """Transactions older than 1 hour must NOT appear in the velocity count."""
    r = redis_lib.Redis.from_url(redis_container.get_connection_url())
    user_id = "window_test_user"
    now = time.time()

    # 3 recent (within 1h), 2 old (>1h ago)
    r.zadd(f"user:{user_id}:txn_ts", {
        "recent_1": now - 100,
        "recent_2": now - 1800,
        "recent_3": now - 3500,
        "old_1": now - 3601,
        "old_2": now - 7200,
    })

    one_hour_ago = now - 3600
    count = r.zcount(f"user:{user_id}:txn_ts", one_hour_ago, "+inf")
    assert count == 3, f"Expected 3 transactions in last hour, found {count}"


def test_velocity_counts_at_multiple_windows(redis_container):
    """Test 1h, 6h, and 24h window counts match expected values."""
    r = redis_lib.Redis.from_url(redis_container.get_connection_url())
    user_id = "multi_window_user"
    now = time.time()

    r.zadd(f"user:{user_id}:txn_ts", {
        "t1": now - 100,        # within 1h, 6h, 24h
        "t2": now - 1800,       # within 1h, 6h, 24h
        "t3": now - 10000,      # outside 1h, within 6h (3600*2.7), within 24h
        "t4": now - 20000,      # outside 1h, outside 6h, within 24h (5.5h)
        "t5": now - 86401,      # outside 24h
    })

    count_1h = r.zcount(f"user:{user_id}:txn_ts", now - 3600, "+inf")
    count_6h = r.zcount(f"user:{user_id}:txn_ts", now - 21600, "+inf")
    count_24h = r.zcount(f"user:{user_id}:txn_ts", now - 86400, "+inf")

    assert count_1h == 2, f"1h count: expected 2, got {count_1h}"
    assert count_6h == 3, f"6h count: expected 3, got {count_6h}"
    assert count_24h == 4, f"24h count: expected 4, got {count_24h}"


def test_user_last_location_stored_and_retrieved(redis_container):
    """User's last known location can be stored and retrieved (geo feature pattern)."""
    r = redis_lib.Redis.from_url(redis_container.get_connection_url())
    user_id = "geo_test_user"

    r.hset(f"user:{user_id}:last_location", mapping={
        "lat": "19.076",
        "lon": "72.877",
        "ts": str(time.time()),
    })

    loc = r.hgetall(f"user:{user_id}:last_location")
    assert b"lat" in loc
    assert float(loc[b"lat"]) == pytest.approx(19.076, abs=0.001)
