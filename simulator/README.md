# Transaction Simulator

## Purpose

The Transaction Simulator is a single-threaded Python service that generates realistic Indian
financial transactions and injects 2-5% fraudulent transactions using five distinct behavioral
patterns. It serves two roles in the fraud detection pipeline:

1. **Kafka publisher** — Streams raw transaction records (without the fraud label) to the
   `transactions` Kafka topic at a configurable rate (default 10 TPS). All downstream services
   (feature enrichment, decision engine) consume from this topic and must never see `is_fraud`.

2. **Training data generator** — Writes a fully-labeled CSV file (with `is_fraud=1/0`) to disk.
   This CSV is the sole source of ground truth for Phase 2 ML model training. The label is
   intentionally withheld from Kafka so the ML pipeline must learn to detect fraud rather than
   receiving it as a signal.

## Quick Start

### Run Locally (requires Kafka running)

```bash
cd simulator/

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment config
cp .env.example .env
# Edit .env: set KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Start the simulator
python main.py
```

The simulator will retry Kafka connection up to 12 times (60 seconds) before exiting.
Stop with Ctrl+C — the process flushes the CSV buffer and drains the Kafka queue before exiting.

### Build Docker Image

```bash
cd simulator/
docker build -t fraud-simulator .
```

### Run with Docker

```bash
docker run \
  --env KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  --env DATA_OUTPUT_PATH=/app/data/transactions.csv \
  --volume $(pwd)/data:/app/data \
  fraud-simulator
```

### Run with Docker Compose (standalone test)

```bash
# Requires an external fraud-detection-network and a healthy Kafka service
docker compose -f docker-compose.simulator.yml up
```

## Architecture

The simulator is split into focused modules:

| Module | Description |
|--------|-------------|
| `config.py` | All environment variable parsing with typed defaults. Every other module imports from here. |
| `cities.py` | `CITIES` dict with lat/lng for 15 major Indian cities used for realistic location simulation. |
| `models.py` | `Transaction` dataclass; `UserProfile`/`UserState` dataclasses; `MerchantRegistry` and `UserRegistry`. |
| `fraud_patterns.py` | `FraudInjector` class implementing all 5 fraud patterns; `haversine_km` distance helper. |
| `kafka_producer.py` | `build_producer`, `produce_transaction`, `flush_producer`, `wait_for_kafka` wrappers. |
| `csv_writer.py` | `CSVWriter` class with 100-transaction buffer and SIGTERM-safe `flush_remaining()`. |
| `main.py` | Entry point: structlog JSON logging, signal handlers, startup retry, main loop, shutdown. |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address (comma-separated for multiple) |
| `KAFKA_TOPIC` | `transactions` | Kafka topic to publish raw transactions to |
| `KAFKA_RETRY_ATTEMPTS` | `12` | Connection retry attempts before exiting (12 x 5s = 60s) |
| `KAFKA_RETRY_INTERVAL_SECONDS` | `5` | Seconds between Kafka connection retry attempts |
| `TXN_RATE` | `10` | Transactions per second (float; e.g., 0.5 = 1 txn every 2s) |
| `FRAUD_RATE` | `0.03` | Fraction of transactions injected as fraudulent (3%) |
| `NUM_USERS` | `1000` | Number of simulated users |
| `NUM_MERCHANTS` | `200` | Number of simulated merchants (partitioned across 6 categories) |
| `RANDOM_SEED` | _(unset)_ | Integer seed for reproducibility; unset = random each run |
| `DATA_OUTPUT_PATH` | `./data/transactions.csv` | Path for labeled CSV output |
| `CSV_FLUSH_INTERVAL` | `100` | Transactions buffered before flushing to CSV |
| `OVERWRITE_CSV` | `false` | Set `true` to overwrite CSV on startup instead of appending |
| `RAPID_FIRE_WINDOW_SECONDS` | `60` | Rapid-fire fraud: time window in seconds |
| `RAPID_FIRE_MIN_TXNS` | `3` | Rapid-fire fraud: minimum transactions within window |
| `AMOUNT_SPIKE_MULTIPLIER` | `10` | Amount spike fraud: multiplier over user's average spend |
| `GEO_VELOCITY_WINDOW_MINUTES` | `10` | Geo-velocity: maximum minutes for impossible travel |
| `GEO_VELOCITY_MAX_KMH` | `900` | Geo-velocity: speed threshold above which travel is impossible |
| `MIDNIGHT_LARGE_START_HOUR` | `1` | Midnight large: window start hour in IST (24h) |
| `MIDNIGHT_LARGE_END_HOUR` | `5` | Midnight large: window end hour in IST (24h, exclusive) |
| `MIDNIGHT_LARGE_MIN_AMOUNT` | `10000` | Midnight large: minimum INR amount |
| `UNUSUAL_MERCHANT_MIN_AMOUNT` | `50000` | Unusual merchant: minimum INR amount for electronics |
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |

## CSV Output Schema

The labeled CSV written to `DATA_OUTPUT_PATH` contains one row per transaction.
Each row has all transaction fields plus the `is_fraud` ground truth label.

| Column | Type | Description |
|--------|------|-------------|
| `transaction_id` | string | UUID4 hex string, globally unique |
| `user_id` | string | Format `user_NNNN` (e.g., `user_0001`) |
| `merchant_id` | string | Format `merchant_NNN` (e.g., `merchant_042`) |
| `amount` | float | Transaction amount in INR, 2 decimal places |
| `currency` | string | Always `INR` |
| `merchant_category` | string | One of: groceries, food, electronics, travel, entertainment, transfers |
| `latitude` | float | Transaction location latitude (city centre ± 0.05°) |
| `longitude` | float | Transaction location longitude (city centre ± 0.05°) |
| `timestamp` | string | ISO 8601 UTC timestamp (e.g., `2026-02-27T14:32:01.123456+00:00`) |
| `device_id` | string | UUID4 hex string |
| `is_international` | bool | Always `False` in simulator v1 |
| `is_fraud` | int | `1` = fraudulent, `0` = legitimate (ground truth label) |

## Kafka Message Schema

Kafka messages published to the `transactions` topic contain the same fields as the CSV
**minus `is_fraud`**. The fraud label is never published to Kafka — downstream consumers
must not receive it.

Message format: JSON-encoded UTF-8, keyed by `user_id` for partition ordering.

```json
{
  "transaction_id": "3f8a2b1c...",
  "user_id": "user_0042",
  "merchant_id": "merchant_015",
  "amount": 1247.50,
  "currency": "INR",
  "merchant_category": "groceries",
  "latitude": 19.0823,
  "longitude": 72.8651,
  "timestamp": "2026-02-27T14:32:01.123456+00:00",
  "device_id": "7d1e9f2a...",
  "is_international": false
}
```

## Fraud Patterns

All 5 patterns are injected at the configured `FRAUD_RATE`. When a pattern cannot fire
(e.g., geo-velocity with no prior location), the injector falls through to another pattern.

| Pattern | Trigger Condition | Fields Modified |
|---------|-------------------|-----------------|
| Rapid-fire | 3 transactions from same user in <60 seconds | `is_fraud=True`; 2 additional burst txns emitted |
| Amount spike | Amount forced to 10x+ user's average spend | `amount` (10–15x avg_spend) |
| Geo-velocity | Transaction placed in a city ≥500 km away within 10 minutes | `latitude`, `longitude` |
| Unusual merchant | Grocery/food user spends ₹50,000+ on electronics | `merchant_id`, `merchant_category`, `amount` |
| Midnight large | Transaction ≥₹10,000 between 1AM–5AM IST | `amount` |

## Indian Cities

The simulator uses real lat/lng coordinates for 15 major Indian cities:

- Mumbai, Delhi, Bengaluru, Chennai, Hyderabad
- Kolkata, Pune, Ahmedabad, Jaipur, Lucknow
- Surat, Nagpur, Visakhapatnam, Kochi, Indore

Transactions are placed at city centres with ±0.05 degree random jitter.
Geo-velocity fraud uses city pairs separated by ≥500 km (e.g., Mumbai–Bengaluru at ~845 km).
