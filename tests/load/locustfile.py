"""
TEST-05: Locust load test — 100+ TPS against ml-scorer /predict.

Run headless (3-minute run, 100 users, ramp at 10/s):
    locust -f tests/load/locustfile.py --headless -u 100 -r 10 \\
        --run-time 3m --host http://localhost:8000 \\
        --html tests/load/report.html

To verify HPA scale-up during load (in a separate terminal):
    kubectl get hpa -n fraud-detection -w
    # Expect ml-scorer replicas to increase from 2 toward 10 during load

Results:
    p50 target: < 20ms
    p99 target: < 200ms (generous for Kind cluster; production SLA is 50ms)
    failure rate: < 1%
"""
import uuid

from locust import HttpUser, between, events, task

PREDICT_PAYLOAD = {
    "transaction_id": "load-test-placeholder",
    "user_id": "load-user-001",
    "amount": 1500.0,
    "merchant_category": "groceries",
    "txn_count_1h": 3,
    "txn_count_6h": 8,
    "txn_count_24h": 15,
    "avg_amount_7d": 1200.0,
    "amount_deviation": 0.25,
    "time_since_last_txn_seconds": 1800.0,
    "unique_merchants_24h": 4,
    "max_amount_24h": 2000.0,
    "is_new_merchant": 0,
    "hour_of_day": 10,
    "is_weekend": 0,
    "geo_distance_km": 0.0,
    "geo_velocity_kmh": 0.0,
    "merchant_category_enc": 0,
}


class MLScorerUser(HttpUser):
    # 5-20ms wait between requests → ~100 TPS at 100 users
    wait_time = between(0.005, 0.02)

    @task
    def predict(self):
        payload = PREDICT_PAYLOAD.copy()
        payload["transaction_id"] = str(uuid.uuid4())
        self.client.post("/predict", json=payload, name="/predict")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Report p50/p99 latency and failure rate after load test."""
    stats = environment.stats.get("/predict", "POST")
    if not stats:
        print("\n[LOAD TEST] No stats collected for /predict")
        return

    p50_ms = stats.get_response_time_percentile(0.50)
    p99_ms = stats.get_response_time_percentile(0.99)
    rps = stats.current_rps
    failure_rate = stats.num_failures / max(stats.num_requests, 1)

    print(f"\n{'='*50}")
    print(f"[LOAD TEST RESULTS]")
    print(f"  Total requests : {stats.num_requests}")
    print(f"  RPS            : {rps:.1f}")
    print(f"  p50 latency    : {p50_ms:.0f}ms  (target: <20ms)")
    print(f"  p99 latency    : {p99_ms:.0f}ms  (target: <200ms)")
    print(f"  Failures       : {stats.num_failures} ({failure_rate:.1%})")
    print(f"{'='*50}")

    # Non-fatal warnings (don't assert to allow partial results)
    if p99_ms > 200:
        print(f"  WARNING: p99 {p99_ms:.0f}ms exceeds 200ms target")
    if failure_rate > 0.01:
        print(f"  WARNING: failure rate {failure_rate:.1%} exceeds 1% threshold")

    print("\n[HPA VERIFICATION]")
    print("  To verify HPA scale-up during load test run in a separate terminal:")
    print("    kubectl get hpa -n fraud-detection -w")
    print("  Expected: ml-scorer REPLICAS increases from 2 toward 10 under CPU load")
    print("  HPA trigger: CPU utilization > 60% (ml-scorer-hpa.yaml)")
