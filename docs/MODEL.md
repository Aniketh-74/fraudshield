# Model Documentation

## Overview

Binary fraud classifier using LightGBM with calibrated probabilities. Trained on synthetic Indian bank transactions with realistic fraud patterns. Outputs a `fraud_probability` in [0, 1] and a `risk_level` (LOW / MEDIUM / HIGH).

## Features

All 14 features are computed at inference time by `feature-enrichment` from Redis user history and the incoming transaction. The exact order in `feature_order.json` must be preserved.

| # | Feature | Description | Source |
|---|---------|-------------|--------|
| 1 | `txn_count_1h` | Transactions by this user in last 1 hour | Redis sorted set ZCOUNT |
| 2 | `txn_count_6h` | Transactions by this user in last 6 hours | Redis sorted set ZCOUNT |
| 3 | `txn_count_24h` | Transactions by this user in last 24 hours | Redis sorted set ZCOUNT |
| 4 | `avg_amount_7d` | Average transaction amount over last 7 days | Redis running average |
| 5 | `amount_deviation` | `(amount - avg_amount_7d) / avg_amount_7d` | Computed |
| 6 | `time_since_last_txn_seconds` | Seconds since user's previous transaction | Redis last timestamp |
| 7 | `unique_merchants_24h` | Distinct merchant IDs in last 24 hours | Redis set cardinality |
| 8 | `max_amount_24h` | Maximum single transaction amount in last 24h | Redis sorted set |
| 9 | `is_new_merchant` | 1 if merchant never seen before for this user | Redis set membership |
| 10 | `hour_of_day` | Hour of transaction (0-23, UTC+5:30) | Transaction timestamp |
| 11 | `is_weekend` | 1 if Saturday or Sunday | Transaction timestamp |
| 12 | `geo_distance_km` | Haversine distance from last known location (km) | Redis last location hash |
| 13 | `geo_velocity_kmh` | `geo_distance_km / time_since_last_txn_seconds * 3600` | Computed |
| 14 | `merchant_category_enc` | Integer encoding of merchant category | `category_mappings.json` |

### Sentinel Values (first transaction per user)

When a user has no history in Redis, sentinel values are used:

| Feature | Sentinel | Rationale |
|---------|----------|-----------|
| `geo_distance_km` | `0.0` | No previous location; distance undefined |
| `geo_velocity_kmh` | `0.0` | No previous location; velocity undefined |
| `time_since_last_txn_seconds` | `-1.0` | Distinguishable from actual 0-second gap |

## Training Methodology

### Dataset
- **Generator:** `transaction-simulator` — synthetic transactions with 5 fraud patterns
- **Size:** ~50,000 transactions (configurable via `NUM_TRANSACTIONS` in training config)
- **Fraud rate:** ~3% (matches realistic India UPI fraud rates)
- **Label:** `is_fraud` (never sent to Kafka; internal to simulator only)

### Pipeline

```
Raw transactions
    │
    ├── Feature computation (same functions as feature-enrichment, copied verbatim)
    │
    ├── Train/test split (80/20, stratified on is_fraud)
    │
    ├── SMOTE oversampling on training set (balance for training only)
    │
    ├── Optuna HPO (100 trials, NopPruner, 5-fold CV on balanced data)
    │   └── Optimizes: AUC-ROC
    │
    ├── LightGBM fit with best hyperparameters
    │
    └── CalibratedClassifierCV (sigmoid, cv=5) on ORIGINAL imbalanced data
        └── Outputs calibrated probabilities at ~3% fraud base rate
```

### Key Decisions

**NopPruner for Optuna** — step-based pruners (MedianPruner, etc.) break with 5-fold CV because Optuna's intermediate value reporting is incompatible with sklearn's cross_val_score iteration. Using NopPruner runs all 100 trials to completion.

**CalibratedClassifierCV on imbalanced data** — calibrating on SMOTE-balanced data would produce wrong ~50% fraud probability estimates. Calibrating on the original ~3% base rate produces outputs where `fraud_probability=0.8` truly means 80% likelihood of fraud.

**Feature parity** — `feature-enrichment/main.py` copies `MERCHANT_CATEGORY_MAP` and `_haversine_km` verbatim from `training/features.py`. Feature drift between training and inference is impossible by construction.

### Model Artifacts

| File | Description |
|------|-------------|
| `training/models/model.txt` | LightGBM native format — used by `ml-scorer` and `shap-explainer` |
| `training/models/calibrated_model.pkl` | sklearn CalibratedClassifierCV wrapper — used only for training metrics |
| `training/models/feature_order.json` | 14 feature names in exact inference order |
| `training/models/category_mappings.json` | Merchant category string → integer encoding |

> **Note:** `calibrated_model.pkl` is NOT used at inference time. The SHAP explainer requires `lgb.Booster` (from `model.txt`) — sklearn's CalibratedClassifierCV wrapper is incompatible with SHAP TreeExplainer.

## Decision Thresholds

| fraud_probability | risk_level | Decision (no rules fired) | Decision (any rule fired) |
|-------------------|------------|---------------------------|---------------------------|
| > 0.7 | HIGH | FLAG | BLOCK |
| 0.3 – 0.7 | MEDIUM | APPROVE | FLAG |
| < 0.3 | LOW | APPROVE | APPROVE |

## Business Rules

Five rules are evaluated before the decision matrix. Each rule fires independently and contributes to the final decision via the matrix above.

| Rule | Trigger Condition | Rationale |
|------|-------------------|-----------|
| `impossible_travel` | `geo_velocity_kmh > 500` | ~845 km Mumbai→Bangalore in < 5 min is physically impossible |
| `velocity_abuse` | `txn_count_1h > 10` | More than 10 transactions per hour is abnormal for an individual |
| `midnight_high_value` | `hour_of_day ∈ [1,2,3,4]` AND `amount > 10000` | High-value transactions at 1-4AM India time are high-risk |
| `amount_spike` | `amount_deviation > 3.0` | Transaction is 3× the user's 7-day average |
| `high_value_new_merchant` | `amount > 50000` AND `is_new_merchant = 1` | Large first-time transaction at unknown merchant |

## Haversine Distance

The geo distance uses the haversine formula. Mumbai (19.076°N, 72.877°E) to Bangalore (12.972°N, 77.580°E) ≈ **845 km** — this value is used as the reference in unit tests (`test_haversine_mumbai_to_bangalore`).

> The original plan documentation cited ~984 km — this was a documentation error. The formula and implementation are correct; the unit test asserts 840–860 km.
