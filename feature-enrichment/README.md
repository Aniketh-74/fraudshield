# Feature Enrichment Service

## Purpose

Consumes raw transactions from the Kafka `transactions` topic, computes 14 real-time features per user via Redis state, and publishes enriched messages to the `enriched-transactions` topic.

This service is part of the fraud detection streaming pipeline. It runs between the transaction simulator and the ML scoring service.

## Features Computed (14 total)

| Feature | Type | Description |
|---|---|---|
| `txn_count_1h` | int | Number of prior transactions by this user in the last 1 hour |
| `txn_count_6h` | int | Number of prior transactions by this user in the last 6 hours |
| `txn_count_24h` | int | Number of prior transactions by this user in the last 24 hours |
| `avg_amount_7d` | float | Rolling average transaction amount over prior 7 days |
| `amount_deviation` | float | (current_amount - avg_7d) / stddev_7d; 0.0 if insufficient history |
| `time_since_last_txn_seconds` | float | Seconds since last transaction; **-1.0 for first transaction** |
| `unique_merchants_24h` | int | Count of distinct merchants used in prior 24 hours |
| `max_amount_24h` | float | Maximum transaction amount in prior 24 hours; 0.0 if none |
| `is_new_merchant` | int | 1 if user has never transacted at this merchant before, else 0 |
| `hour_of_day` | int | Hour of day in IST (Asia/Kolkata, UTC+5:30), 0-23 |
| `is_weekend` | int | 1 if Saturday or Sunday (IST), else 0 |
| `geo_distance_km` | float | Haversine distance from last transaction location; **0.0 for first** |
| `geo_velocity_kmh` | float | Speed implied by distance/time; **0.0 for first**; capped at 2000 km/h |
| `merchant_category_enc` | int | Encoded merchant category: groceries=0, food=1, electronics=2, travel=3, entertainment=4, transfers=5; -1 for unknown |

### Sentinel Values for First Transaction per User

- `geo_distance_km = 0.0` (no prior location = no travel = neutral)
- `geo_velocity_kmh = 0.0` (no prior location = no velocity = neutral)
- `time_since_last_txn_seconds = -1.0` (distinguishable from 0 = "just happened")

## Environment Variables

See `.env.example` for all variables with defaults.

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_INPUT_TOPIC` | `transactions` | Topic to consume raw transactions from |
| `KAFKA_OUTPUT_TOPIC` | `enriched-transactions` | Topic to publish enriched transactions to |
| `KAFKA_GROUP_ID` | `feature-enrichment-group` | Consumer group ID |
| `KAFKA_RETRY_ATTEMPTS` | `12` | Max Kafka connection attempts at startup |
| `KAFKA_RETRY_INTERVAL_SECONDS` | `5` | Seconds between Kafka retry attempts |
| `KAFKA_MIN_COMMIT_COUNT` | `10` | Commit offsets every N messages |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `REDIS_RETRY_ATTEMPTS` | `3` | Max Redis connection attempts at startup |
| `REDIS_RETRY_BACKOFF_SECONDS` | `1.0` | Base backoff for Redis retry (doubles each attempt) |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Running Locally

```bash
pip install -r requirements.txt
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 REDIS_URL=redis://localhost:6379 python main.py
```

Or with a `.env` file (requires `python-dotenv`):
```bash
cp .env.example .env
python -c "from dotenv import load_dotenv; load_dotenv()" && python main.py
```

## Running with Docker

```bash
# Build
docker build -t feature-enrichment .

# Run (requires Kafka and Redis already running)
docker run --network host \
  -e KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  -e REDIS_URL=redis://localhost:6379 \
  feature-enrichment
```

## Redis Key Structure

| Key | Type | TTL | Contents |
|---|---|---|---|
| `user:{id}:velocity` | Hash | 1 hour | `txn_count_1h`, `txn_count_6h`, `txn_count_24h`, `unique_merchants_24h`, `max_amount_24h` |
| `user:{id}:profile` | Hash | 7 days | `last_ts_epoch`, `last_lat`, `last_lng`, `avg_amount_7d`, `amount_sum_7d`, `amount_count_7d` |
| `user:{id}:txn_ts` | Sorted Set | 25 hours | score=epoch, member=transaction_id — used for txn_count_1h/6h/24h |
| `user:{id}:amounts_24h` | Sorted Set | 25 hours | score=epoch, member=`{epoch}:{amount}` — used for max_amount_24h and amount_deviation stddev |
| `user:{id}:merchants_24h` | Sorted Set | 25 hours | score=epoch, member=merchant_id — used for unique_merchants_24h |
| `user:{id}:seen_merchants` | Set | No TTL | All merchant_ids ever seen by user — used for is_new_merchant |

## Output Message Format

Enriched messages contain all original transaction fields PLUS all 14 feature fields. The `is_fraud` field is never present (the simulator strips it before Kafka; this service does not add it).

Example enriched message:
```json
{
  "transaction_id": "abc123",
  "user_id": "user_0001",
  "merchant_id": "merchant_042",
  "amount": 1500.00,
  "currency": "INR",
  "merchant_category": "groceries",
  "latitude": 19.076,
  "longitude": 72.877,
  "timestamp": "2026-01-15T14:30:00Z",
  "device_id": "dev_xyz",
  "is_international": false,
  "txn_count_1h": 2,
  "txn_count_6h": 5,
  "txn_count_24h": 12,
  "avg_amount_7d": 1200.0,
  "amount_deviation": 0.42,
  "time_since_last_txn_seconds": 3600.0,
  "unique_merchants_24h": 4,
  "max_amount_24h": 2000.0,
  "is_new_merchant": 0,
  "hour_of_day": 20,
  "is_weekend": 0,
  "geo_distance_km": 15.3,
  "geo_velocity_kmh": 55.1,
  "merchant_category_enc": 0
}
```
