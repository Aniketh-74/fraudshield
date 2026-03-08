# shap-explainer

Polls PostgreSQL for FLAG/BLOCK decisions that have not yet received SHAP explanations
(shap_values = '[]'), computes top-5 SHAP feature contributions using the native
LightGBM Booster (model.txt), and stores them in the shap_values JSONB column.

## Architecture

This service is intentionally separate from the decision-engine Kafka consumer to avoid
blocking message processing. SHAP computation runs asynchronously on a polling loop.

## Quick start (Docker Compose)

    docker compose up shap-explainer

## Prerequisites

- PostgreSQL `decisions` table must have the `shap_values` JSONB column added by
  `infra/postgres/02-phase4-columns.sql` (part of Phase 4 04-01 plan)
- Model artifacts must be present at MODEL_DIR (default: /app/models):
  - model.txt  — native LightGBM Booster (from training phase)
  - feature_order.json  — list of 14 feature names

## Environment variables

See `.env.example` for all variables.

| Variable | Default | Description |
|---|---|---|
| DATABASE_URL | postgresql://... | PostgreSQL DSN |
| MODEL_DIR | /app/models | Directory containing model.txt and feature_order.json |
| SHAP_POLL_INTERVAL_SECONDS | 5 | Seconds to wait between polls when no rows found |
| SHAP_BATCH_SIZE | 50 | Max rows to process per poll batch |

## SHAP output format

Each processed decision gets a `shap_values` array of 5 objects:

    [
      {"feature": "geo_velocity_kmh", "value": 0.482341},
      {"feature": "amount_deviation",  "value": -0.231045},
      ...
    ]

Sorted by abs(value) descending. Positive = pushes toward fraud prediction.
Negative = pushes away from fraud prediction.

## Model artifact note

Uses model.txt (native LightGBM Booster), NOT calibrated_model.pkl.
SHAP TreeExplainer requires direct tree access and cannot interpret sklearn
CalibratedClassifierCV wrappers.
