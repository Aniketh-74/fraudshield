# API Reference

Base URL (Docker Compose): `http://localhost:8000`
Base URL (Kubernetes): `http://localhost/api-gateway` (via Ingress)

All responses are JSON. All timestamps are ISO 8601 UTC.

---

## REST Endpoints

### GET /health

Health check.

**Response:**
```json
{"status": "ok"}
```

---

### GET /api/transactions/recent

Recent fraud decisions, newest first.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Number of transactions to return (max 200) |
| `offset` | int | 0 | Pagination offset |

**Response:** Array of `TransactionSummary`

```json
[
  {
    "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user_042",
    "amount": 45000.00,
    "fraud_probability": 0.87,
    "risk_level": "HIGH",
    "decision": "BLOCK",
    "fired_rules": ["impossible_travel", "velocity_abuse"],
    "created_at": "2026-03-07T14:23:01.123456Z",
    "location_lat": 19.076,
    "location_lng": 72.877
  }
]
```

**Example:**
```bash
curl "http://localhost:8000/api/transactions/recent?limit=10"
```

---

### GET /api/metrics/summary

Aggregated fraud pipeline metrics.

**Response:** `MetricsSummary`

```json
{
  "total_transactions": 12847,
  "fraud_rate": 0.034,
  "flagged_count": 231,
  "blocked_count": 198,
  "approved_count": 12418,
  "avg_latency_ms": 38.2,
  "review_queue_count": 14
}
```

**Example:**
```bash
curl http://localhost:8000/api/metrics/summary
```

---

### GET /api/stats/hourly

Transaction counts by decision type, grouped by hour (last 24 hours).

**Response:** Array of `HourlyStat`

```json
[
  {"hour": "2026-03-07T13:00:00Z", "decision": "APPROVE", "count": 412},
  {"hour": "2026-03-07T13:00:00Z", "decision": "FLAG", "count": 18},
  {"hour": "2026-03-07T13:00:00Z", "decision": "BLOCK", "count": 11}
]
```

**Example:**
```bash
curl http://localhost:8000/api/stats/hourly
```

---

### GET /api/transactions/flagged

Transactions in the analyst review queue (decision=FLAG, not yet reviewed).

**Response:** Array of `TransactionSummary` (same schema as `/recent`)

**Example:**
```bash
curl http://localhost:8000/api/transactions/flagged
```

---

### GET /api/transactions/{transaction_id}

Full transaction detail including SHAP values and analyst review outcome.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | UUID string | Transaction identifier |

**Response:** `TransactionDetail`

```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_042",
  "amount": 45000.00,
  "fraud_probability": 0.87,
  "risk_level": "HIGH",
  "decision": "FLAG",
  "fired_rules": ["velocity_abuse"],
  "created_at": "2026-03-07T14:23:01.123456Z",
  "location_lat": 19.076,
  "location_lng": 72.877,
  "feature_vector": {
    "txn_count_1h": 14,
    "amount_deviation": 3.8,
    "geo_velocity_kmh": 0.0
  },
  "shap_values": [0.23, -0.05, 0.41, 0.12, -0.08, 0.31, 0.07, -0.02, 0.15, 0.03, -0.01, 0.0, 0.0, 0.18],
  "analyst_decision": null,
  "analyst_id": null,
  "reviewed_at": null,
  "processing_latency_ms": 38.7
}
```

> **Note:** `shap_values` is `null` until the SHAP explainer processes the transaction (typically within 1-2 seconds for FLAG/BLOCK decisions). APPROVE decisions never receive SHAP values.

**Example:**
```bash
curl http://localhost:8000/api/transactions/550e8400-e29b-41d4-a716-446655440000
```

---

### POST /api/transactions/{transaction_id}/review

Submit analyst review decision for a flagged transaction.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | UUID string | Must be a FLAG decision |

**Request Body:**

```json
{
  "decision": "CONFIRMED_FRAUD",
  "analyst_id": "analyst-1"
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `decision` | string | `CONFIRMED_FRAUD`, `FALSE_POSITIVE` | Analyst outcome |
| `analyst_id` | string | any | Analyst identifier (default: `"analyst-1"`) |

**Response:**

```json
{"status": "ok"}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/transactions/550e8400-e29b-41d4-a716-446655440000/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "FALSE_POSITIVE", "analyst_id": "analyst-1"}'
```

---

## WebSocket: /ws/live

Real-time stream of fraud decisions as they are processed.

**Connection:**
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/live");
```

**Message format** (server → client, JSON string):

```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_042",
  "amount": 45000.00,
  "merchant_category": "electronics",
  "fraud_probability": 0.87,
  "risk_level": "HIGH",
  "decision": "BLOCK",
  "fired_rules": ["impossible_travel"],
  "timestamp": "2026-03-07T14:23:01.123456Z",
  "location": {"lat": 19.076, "lng": 72.877}
}
```

**Behavior:**
- Messages flow server → client only (client sends keep-alive text; server ignores it)
- Only new decisions are broadcast (no historical replay — `auto_offset_reset=latest`)
- All connected clients receive all messages (broadcast pattern)
- Reconnect automatically on disconnect

**Example (browser console):**
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/live");
ws.onmessage = (event) => {
  const decision = JSON.parse(event.data);
  console.log(decision.decision, decision.fraud_probability);
};
```
