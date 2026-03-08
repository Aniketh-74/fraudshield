# ML Scoring Service

FastAPI service that loads a calibrated LightGBM model and returns fraud probability for enriched transactions.

## Endpoints

| Method | Path       | Description                          |
|--------|------------|--------------------------------------|
| POST   | /predict   | Fraud probability prediction         |
| GET    | /health    | Liveness probe (model_loaded status) |
| GET    | /metrics   | Prometheus metrics                   |

### POST /predict

Accepts enriched transaction JSON with all 14 feature fields. Returns:

```json
{
  "fraud_probability": 0.042,
  "risk_level": "LOW",
  "model_version": "v20260301"
}
```

### Risk Levels

| Level  | Probability Range |
|--------|-------------------|
| LOW    | < 0.3             |
| MEDIUM | 0.3 – 0.7         |
| HIGH   | > 0.7             |

## Required Environment Variables

| Variable             | Default        | Description                          |
|----------------------|----------------|--------------------------------------|
| `MODEL_DIR`          | `/app/models`  | Directory containing model artifacts |
| `PORT`               | `8000`         | HTTP server port                     |
| `HOST`               | `0.0.0.0`      | HTTP server bind address             |
| `WORKERS`            | `1`            | Uvicorn workers (1 = not fork-safe)  |
| `RISK_LOW_THRESHOLD` | `0.3`          | Probability below which = LOW        |
| `RISK_HIGH_THRESHOLD`| `0.7`          | Probability above which = HIGH       |
| `LOG_LEVEL`          | `INFO`         | Structured log level                 |

## Model Files Required in MODEL_DIR

- `calibrated_model.pkl` — CalibratedClassifierCV (sklearn + LightGBM)
- `feature_order.json` — List of 14 feature name strings
- `model_version.txt` — (optional) version label; falls back to pkl mtime

## How to Run Locally

```bash
# Run with training output mounted as model directory
MODEL_DIR=./training/models python main.py
```

## SLA

- p99 latency: < 50ms (expected 5–15ms for sklearn predict_proba)
- Measured via `prediction_latency_seconds` Prometheus histogram

## Example Request

```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "t1",
    "user_id": "u1",
    "txn_count_1h": 0.0,
    "txn_count_6h": 0.0,
    "txn_count_24h": 0.0,
    "avg_amount_7d": 1000.0,
    "amount_deviation": 0.0,
    "time_since_last_txn_seconds": -1.0,
    "unique_merchants_24h": 0.0,
    "max_amount_24h": 0.0,
    "is_new_merchant": 1.0,
    "hour_of_day": 14.0,
    "is_weekend": 0.0,
    "geo_distance_km": 0.0,
    "geo_velocity_kmh": 0.0,
    "merchant_category_enc": 0.0
  }'
```

## Docker

```bash
# Build image
docker build -t ml-scorer .

# Run with model volume mount
docker run -p 8000:8000 \
  -v $(pwd)/training/models:/app/models:ro \
  ml-scorer
```
