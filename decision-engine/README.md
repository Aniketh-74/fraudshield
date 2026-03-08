# decision-engine

Consumes enriched transactions from Kafka, calls the ML scorer, applies 5 configurable
business rules, writes FLAG/BLOCK decisions to PostgreSQL, publishes decisions to Kafka,
and broadcasts live decisions via WebSocket.

## Quick start (Docker Compose)

    docker compose up decision-engine

## Environment variables

See `.env.example` for all variables. Key overrides:

| Variable | Default | Description |
|---|---|---|
| SCORER_URL | http://localhost:8000 | ML scorer service base URL |
| DATABASE_URL | postgresql://... | PostgreSQL DSN |
| RULES_CONFIG_PATH | /app/rules.yaml | Path to YAML rules config |
| WS_PORT | 8765 | WebSocket server port |

## Hot-reloading rules

Edit `rules.yaml` and save. The watchdog thread detects the file change and reloads
rules atomically without restarting the service. Check logs for `rules_loaded` event.

## PostgreSQL migration

If postgres_data volume already exists from Phase 3, run the migration manually:

    docker exec postgres psql -U postgres -d frauddb \
      -f /docker-entrypoint-initdb.d/02-phase4-columns.sql

On fresh installs (docker compose down -v && docker compose up), the migration runs
automatically via docker-entrypoint-initdb.d.

## WebSocket output

Connect to ws://localhost:8765 to receive live decision events:

    {"transaction_id": "...", "user_id": "...", "amount": 1234.56,
     "fraud_probability": 0.82, "risk_level": "HIGH", "decision": "BLOCK",
     "fired_rules": ["impossible_travel"], "timestamp": "2026-03-05T...Z"}

All decisions are streamed (APPROVE + FLAG + BLOCK). SHAP values are not included
here; they are computed by the shap-explainer service and stored in PostgreSQL.

## Known limitation

`is_international` is not computed by the feature-enrichment service (Phase 3).
The `high_value_new_merchant` rule defaults is_international=0 and will never fire
until international detection is added in a future phase.
