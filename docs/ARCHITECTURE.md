# Architecture

## Overview

The fraud detection pipeline is an event-driven microservices system built around Apache Kafka as the central message bus. Transactions flow through six specialized services before appearing on a live dashboard. Every component is stateless and horizontally scalable.

The guiding design principle: **each service does one thing and does it well**. The ML scorer only scores. The decision engine only applies rules. The SHAP explainer only explains. This separation means each service can be scaled, tested, replaced, or debugged independently.

## Component Boundaries

### Transaction Simulator
- **Responsibility:** Generate synthetic Indian bank transactions at configurable TPS
- **Input:** None (internal timer)
- **Output:** `transactions` Kafka topic (JSON, no `is_fraud` field — label never leaves simulator)
- **Scaling:** 1 replica (rate-controlled via sleep)

### Feature Enrichment
- **Responsibility:** Compute user velocity features from Redis history; enrich transaction with geo and temporal features
- **Input:** `transactions` Kafka topic
- **Output:** `enriched-transactions` Kafka topic; Redis sorted sets and hashes updated
- **Scaling:** HPA 2-5 replicas (CPU target 70%)
- **State:** Redis — `user:{id}:txn_ts` sorted set (ZADD, ZCOUNT), `user:{id}:last_location` hash

### ML Scorer
- **Responsibility:** Score a feature vector with the LightGBM model; return fraud probability and risk level
- **Input:** HTTP POST `/predict` (synchronous, called by decision engine)
- **Output:** `{"fraud_probability": 0.82, "risk_level": "HIGH"}`
- **Scaling:** HPA 2-10 replicas (CPU target 60%)
- **Key decision:** Sync `def` handler (not async) — CPU-bound sklearn predict_proba runs in FastAPI thread pool

### Decision Engine
- **Responsibility:** Apply 5 business rules + ML score matrix; write final decision to PostgreSQL; broadcast to Kafka
- **Input:** `enriched-transactions` Kafka topic; HTTP calls to ml-scorer
- **Output:** `decisions` Kafka topic; PostgreSQL `transactions` table row
- **Scaling:** 2 replicas (stateless, fail-open on ML scorer failure)
- **Key decision:** Fail-open pattern — if ml-scorer returns error, decision engine APPROVEs with sentinel score (never silently drops)

### SHAP Explainer
- **Responsibility:** Compute SHAP waterfall values for FLAG/BLOCK decisions asynchronously
- **Input:** PostgreSQL `transactions` table (polls `WHERE shap_values IS NULL AND decision != 'APPROVE'`)
- **Output:** PostgreSQL `shap_values` column updated
- **Scaling:** 1 replica (polling architecture, `FOR UPDATE SKIP LOCKED` handles multiple instances)
- **Key decision:** `FOR UPDATE SKIP LOCKED` — multiple replicas process different rows without deadlocks

### API Gateway
- **Responsibility:** Serve REST API and WebSocket live feed to the dashboard
- **Input:** HTTP from dashboard; Kafka `decisions` topic (via internal consumer)
- **Output:** REST responses; WebSocket messages
- **Key decision:** asyncpg with `_init_connection` JSONB codec — JSONB fields return Python dicts directly, not strings

### React Dashboard
- **Responsibility:** Display live fraud pipeline activity with charts, maps, and analyst tools
- **Input:** REST API (`/api/`), WebSocket (`/ws/live`)
- **Key components:** LiveFeed, TimeSeriesChart, PieChart, RulesChart, HeatmapChart (custom SVG), IndiaMap (Leaflet CircleMarker), TransactionDrawer (SHAP waterfall), FlagQueue (analyst review)

## Data Flow

```
1. Simulator generates transaction (INR, India geography, 2-5% fraud rate)
   → Publishes to Kafka `transactions` topic

2. Feature Enrichment consumes transaction
   → Reads user history from Redis (sorted sets for velocity, hash for last location)
   → Computes 13 user-history features + merchant_category_enc
   → Updates Redis with new transaction timestamp and location
   → Publishes enriched features to Kafka `enriched-transactions`

3. Decision Engine consumes enriched transaction
   → Calls ML Scorer HTTP /predict (synchronous, fail-open)
   → Applies 5 business rules (impossible_travel, velocity_abuse, midnight_high_value, amount_spike, high_value_new_merchant)
   → Applies decision matrix: ML score × rules fired → APPROVE/FLAG/BLOCK
   → Writes decision row to PostgreSQL
   → Publishes decision to Kafka `decisions`

4. SHAP Explainer polls PostgreSQL
   → Finds decisions with shap_values IS NULL AND decision != APPROVE
   → Computes SHAP values using lgb.Booster (native, not sklearn wrapper)
   → Updates PostgreSQL shap_values column

5. API Gateway consumes Kafka `decisions`
   → Broadcasts each decision via WebSocket to all connected dashboard clients
   → Serves historical data via REST from PostgreSQL

6. Dashboard receives WebSocket message
   → Updates LiveFeed, charts, and map in real time
   → Analyst can click FLAG row → TransactionDrawer opens with SHAP waterfall
   → Analyst submits Confirm Fraud / False Positive → PATCH /api/transactions/{id}/review
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Fail-open ML scorer | Never drop a transaction; approve with sentinel score if scorer is unreachable |
| asyncpg JSONB codec | `_init_connection` registers codec; bypassing `db.create_pool` breaks JSONB deserialization |
| SHAP uses lgb.Booster (not pkl) | sklearn CalibratedClassifierCV wrapper incompatible with SHAP TreeExplainer |
| `FOR UPDATE SKIP LOCKED` in SHAP | Enables multiple SHAP explainer replicas without deadlocks |
| Redis EXPIRE nx=True | Prevents TTL reset on repeated writes; preserves time-window accuracy |
| Kafka compression: none | aiokafka cannot decode lz4/snappy without native C extensions |
| CircleMarker (not Marker) in Leaflet | SVG circle; no PNG icon files needed; eliminates broken-image in Vite |
| HeatmapChart as custom SVG | Recharts has no native heatmap; 24×7 grid built as SVG rects |

## Infrastructure

### Kind Cluster (`kind-config.yaml`)
- Single control-plane node with `extraPortMappings` (ports 80/443) — must be set at cluster creation
- Node label `ingress-ready=true` for ingress-nginx

### Kubernetes Namespace: `fraud-detection`
All services, ConfigMaps, Secrets, and monitoring resources live in this namespace.

### Auto-Scaling
- `ml-scorer` HPA: minReplicas=2, maxReplicas=10, CPU target=60%
- `feature-enrichment` HPA: minReplicas=2, maxReplicas=5, CPU target=70%
- metrics-server patched with `--kubelet-insecure-tls` (required in Kind)

### NetworkPolicy
- PostgreSQL accessible only from: api-gateway, decision-engine, shap-explainer
- Redis accessible only from: feature-enrichment, ml-scorer

### Monitoring
- Prometheus: kubernetes_sd_configs pod role, annotation-based scrape filtering
- Grafana: 3-ConfigMap provisioning pattern (datasource + provider + dashboard JSON)
- Anonymous viewer access enabled for recruiter demos
