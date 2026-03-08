# FraudShield — Real-Time Fraud Detection Platform

<div align="center">

![FraudShield Banner](https://img.shields.io/badge/FraudShield-Real--Time%20Fraud%20Detection-4F8EF7?style=for-the-badge&logo=shield&logoColor=white)

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Online-20C997?style=for-the-badge&logo=vercel&logoColor=white)](https://suzie-unmaddened-consumingly.ngrok-free.dev)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-Event%20Stream-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![LightGBM](https://img.shields.io/badge/LightGBM-AUC%200.954-9B6DFF?style=for-the-badge&logo=python&logoColor=white)](https://lightgbm.readthedocs.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)

**A production-grade, end-to-end fraud detection system that processes transactions in real time, scores them with a machine learning model, explains every decision with AI, and lets human analysts review flagged cases — all visible on a live dashboard.**

[View Live Demo](https://suzie-unmaddened-consumingly.ngrok-free.dev) · [Architecture](#architecture) · [Quick Start](#quick-start) · [How It Works](#how-it-works)

</div>

---

## What Is This?

Imagine you swipe your card at a store. In the next **23 milliseconds**, this system:

1. **Receives** your transaction
2. **Enriches** it with your spending history (how often you transact, your average spend, etc.)
3. **Scores** it using a machine learning model trained on 590,000 real fraud cases
4. **Applies** business rules (unusual location? amount spike? new merchant?)
5. **Decides**: APPROVE, FLAG for human review, or BLOCK
6. **Explains** the decision using SHAP AI — so analysts know *why* it was flagged
7. **Displays** everything live on a dashboard that anyone can watch in real time

This is how real banks and fintech companies (Stripe, Razorpay, PhonePe) detect fraud at scale.

---

## Live Dashboard

> **Try it now:** [https://suzie-unmaddened-consumingly.ngrok-free.dev](https://suzie-unmaddened-consumingly.ngrok-free.dev)

The dashboard shows:

| Panel | What it shows |
|---|---|
| **Live Feed** | Every transaction as it happens, color-coded by decision |
| **Flag Queue** | Transactions waiting for human analyst review |
| **India Map** | Geographic heatmap of transaction locations |
| **Decision Distribution** | Pie chart: APPROVE / FLAG / BLOCK ratio |
| **Fraud by Hour** | When fraud spikes during the day |
| **Rule Triggers** | Which business rules are firing most |
| **Transaction Detail** | Full breakdown + SHAP waterfall chart for any transaction |

---

## Architecture

```
  Every 100ms a simulated transaction is generated
                        │
                        ▼
            ┌─────────────────────┐
            │  Transaction        │   Generates realistic Indian payment
            │  Simulator          │   transactions + injects fraud patterns
            └──────────┬──────────┘
                       │ Kafka: transactions
                        ▼
            ┌─────────────────────┐
            │  Feature            │   Computes 14 behavioral features:
            │  Enrichment         │   spend velocity, geo distance, burst rate
            └──────┬──────────────┘
                   │◄──── Redis (sub-ms feature cache)
                   │ Kafka: enriched-transactions
                    ▼
            ┌─────────────────────┐
            │  ML Scorer          │   LightGBM model → fraud_probability 0–1
            │  (LightGBM)         │   AUC: 0.954, latency: <5ms
            └──────────┬──────────┘
                       │ fraud probability + risk level
                        ▼
            ┌─────────────────────┐
            │  Decision Engine    │   ML score + business rules → decision
            │  + Rules Engine     │   APPROVE / FLAG / BLOCK
            └──────┬──────────────┘
                   │           │
          Kafka: decisions      │ writes to DB
                   │           ▼
                   │    ┌──────────────┐    ┌─────────────────┐
                   │    │  PostgreSQL  │◄───│  SHAP Explainer │
                   │    │  (decisions) │    │  (runs async,   │
                   │    └──────┬───────┘    │  explains why)  │
                   │           │            └─────────────────┘
                    ▼          │
            ┌─────────────────────┐
            │  API Gateway        │   FastAPI REST + WebSocket
            │  (FastAPI)          │   Single entry point for frontend
            └──────────┬──────────┘
                       │
                        ▼
            ┌─────────────────────┐
            │  React Dashboard    │   Live feed, charts, map,
            │  (port 3000)        │   analyst review workflow
            └─────────────────────┘
```

### All Services

| Service | Tech | What it does |
|---|---|---|
| **Transaction Simulator** | Python | Creates 10 transactions/sec with realistic fraud patterns |
| **Feature Enrichment** | Python + Redis | Computes behavioral signals per user in real time |
| **ML Scorer** | LightGBM + FastAPI | Returns fraud probability in <5ms |
| **Decision Engine** | Python + Kafka | Combines ML + rules → final verdict |
| **SHAP Explainer** | SHAP + asyncpg | Explains every decision (runs async in background) |
| **API Gateway** | FastAPI + WebSocket | REST API + live WebSocket stream |
| **Dashboard** | React + Recharts | Live fraud monitoring + analyst UI |
| **PostgreSQL** | Postgres 16 | Stores all decisions, features, SHAP values, reviews |
| **Redis** | Redis 7 | Sub-millisecond feature cache |
| **Kafka** | Confluent Kafka | Event backbone connecting all services |

---

## How It Works

### Step 1 — A transaction happens
The simulator generates realistic Indian payment transactions every 100ms. It randomly injects fraud with these patterns:

| Pattern | What it looks like |
|---|---|
| `amount_spike` | User who spends ₹2,000 on average suddenly does a ₹4,00,000 transaction |
| `geo_velocity` | Transaction in Mumbai, then another in Chennai 8 minutes later (physically impossible) |
| `rapid_fire` | 20 transactions in 60 seconds (card testing attack) |
| `unusual_merchant` | First-ever transaction at a crypto exchange or overseas wire service |

### Step 2 — Features are computed
The Feature Enrichment service enriches each transaction with behavioral context pulled from Redis:

```
txn_count_1h          →  How many transactions did this user make in the last hour?
avg_amount_7d         →  What's their average spend over 7 days?
amount_deviation      →  How many standard deviations above average is this amount?
geo_velocity_kmh      →  How fast would they have to travel between their last two locations?
time_since_last_txn   →  How many seconds since their previous transaction?
is_new_merchant       →  Is this their first time at this merchant?
```

### Step 3 — ML Model scores it
A **LightGBM** model trained on 590,540 real transactions from the [IEEE-CIS Fraud Detection dataset](https://www.kaggle.com/c/ieee-fraud-detection) returns a fraud probability between 0 and 1.

- **AUC: 0.954** (industry-grade — top Kaggle submissions reach ~0.96)
- Tuned with **Optuna** over 50 trials
- Calibrated with isotonic regression for accurate probability estimates

### Step 4 — Business rules are applied
Even a low ML score can be overridden by rules. The decision matrix:

```
fraud_probability > 0.7  (HIGH)   + rule fired  →  BLOCK
fraud_probability > 0.7  (HIGH)   + no rule     →  FLAG
fraud_probability 0.3–0.7 (MEDIUM) + rule fired →  FLAG
fraud_probability 0.3–0.7 (MEDIUM) + no rule    →  APPROVE
fraud_probability < 0.3  (LOW)    (any)         →  APPROVE
```

### Step 5 — Decision is explained
The SHAP Explainer runs in the background and computes a waterfall chart for every flagged transaction — showing exactly which features pushed the fraud score up or down:

```
Base fraud rate:  +0.05
amount_deviation: +0.31  ← This transaction is 8x the user's average amount
geo_velocity_kmh: +0.18  ← Location changed 700km in 10 minutes
txn_count_1h:     +0.09  ← 12 transactions in the last hour
avg_amount_7d:    -0.02  ← Their 7-day average is moderate (slightly reassuring)
────────────────────────
Final score:       0.61  → FLAG for analyst review
```

### Step 6 — Analyst reviews it
The **Flag Queue** tab shows all unreviewed flagged transactions. An analyst sees the fraud %, rules fired, and amount. They click to open the full detail drawer and can:
- **Confirm Fraud** → records their decision, removes from queue
- **Mark False Positive** → clears it, feeds back into the system

---

## Quick Start

### You need
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — the only requirement
- 8GB RAM available

### 3 commands to run the full system

```bash
# 1. Get the code
git clone https://github.com/Aniketh-74/fraudshield.git
cd fraudshield

# 2. Start all 12 services
docker compose up -d

# 3. Open the dashboard
# Visit http://localhost:3000 in your browser
```

Docker will download everything automatically. First run takes 3–5 minutes. After that, startup is ~30 seconds.

You'll see transactions flowing immediately in the Live Feed. Within 60 seconds, the charts and map will populate.

### Stop everything
```bash
docker compose down          # stops services, keeps your data
docker compose down -v       # stops services AND deletes all data (fresh start)
```

---

## Project Structure

```
fraudshield/
│
├── simulator/              # Generates fake transactions with fraud patterns
├── feature-enrichment/     # Computes behavioral features using Redis
├── ml-scorer/              # Serves the LightGBM model via FastAPI
├── decision-engine/        # Rules engine + ML score → final decision
├── shap-explainer/         # Async SHAP value computation
├── api-gateway/            # FastAPI REST API + WebSocket server
│
├── dashboard/              # React frontend
│   └── src/
│       ├── components/
│       │   ├── LiveFeed.jsx          # Real-time transaction stream
│       │   ├── FlagQueue.jsx         # Analyst review panel
│       │   ├── TransactionDrawer.jsx # Full transaction detail + SHAP
│       │   ├── IndiaMap.jsx          # Geographic transaction map
│       │   └── ShapWaterfall.jsx     # SHAP explanation waterfall chart
│       └── api/client.js             # API calls to backend
│
├── training/               # ML model training pipeline
│   ├── train.py            # LightGBM + Optuna training script
│   ├── features.py         # Feature engineering
│   └── models/             # Trained model artifacts (calibrated_model.pkl)
│
├── infra/
│   ├── postgres/init.sql   # Full database schema
│   └── nginx/nginx.conf    # Production reverse proxy config
│
├── docker-compose.yml      # Local development
├── docker-compose.prod.yml # Production (Nginx on port 80)
└── deploy.sh               # One-shot Linux server setup script
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/metrics/summary` | GET | Aggregate stats: total, fraud rate, latency, queue size |
| `/api/transactions/recent?limit=200` | GET | Latest N decisions |
| `/api/transactions/flagged` | GET | Unreviewed FLAG transactions |
| `/api/transactions/{id}` | GET | Full detail including SHAP values |
| `/api/transactions/{id}/review` | POST | Submit analyst review |
| `/api/metrics/hourly` | GET | Per-hour counts for last 24h |
| `/ws/live` | WebSocket | Real-time stream of all decisions |

### Quick example
```bash
# Get current system metrics
curl http://localhost:3000/api/metrics/summary
```
```json
{
  "total_transactions": 15420,
  "fraud_rate": 0.082,
  "flagged_count": 823,
  "blocked_count": 442,
  "approved_count": 14155,
  "avg_latency_ms": 23.4,
  "review_queue_count": 310
}
```

### Connect to the live stream
```javascript
const ws = new WebSocket('ws://localhost:3000/ws/live')
ws.onmessage = (e) => {
  const txn = JSON.parse(e.data)
  console.log(`${txn.decision} | ₹${txn.amount} | fraud: ${(txn.fraud_probability*100).toFixed(1)}%`)
}
// APPROVE | ₹2340   | fraud: 2.1%
// FLAG    | ₹87500  | fraud: 71.3%
// BLOCK   | ₹420000 | fraud: 94.7%
```

---

## ML Model Details

### Dataset
The model is trained on the [IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection) dataset — real transaction data provided by Vesta Corporation:
- **590,540** transactions
- **3.5%** fraud rate (severely imbalanced)
- Mix of transaction + identity features

### Training pipeline
```
Raw IEEE-CIS data
  → 32 engineered features (temporal, behavioral, card metadata)
  → 80/20 stratified train/validation split
  → SMOTE oversampling (fix class imbalance)
  → Optuna hyperparameter search (50 trials, maximize AUC)
  → LightGBM training on best hyperparameters
  → CalibratedClassifierCV (isotonic regression) for probability calibration
  → Export: calibrated_model.pkl + feature_order.json
```

### Results

| Metric | Value |
|---|---|
| ROC-AUC | **0.954** |
| Training samples | 472,432 |
| Validation samples | 118,108 |
| Hyperparameter trials | 50 (Optuna) |
| Inference latency | <5ms per transaction |

### Retrain the model yourself
```bash
# Download IEEE-CIS dataset from Kaggle into training/data/
# Then run:
docker compose --profile training up training
```

---

## Deployment

### Share with ngrok (instant public URL)
```bash
ngrok http 3000
# Dashboard live at https://xxxx.ngrok-free.app
```

### Deploy to any Linux server (Ubuntu 22.04)
```bash
git clone https://github.com/Aniketh-74/fraudshield.git
cd fraudshield
bash deploy.sh
# Dashboard live at http://YOUR_SERVER_IP
```

The `deploy.sh` script automatically installs Docker, opens firewall ports, and starts all services.

---

## Useful Commands

```bash
# View logs from all services
docker compose logs -f

# View logs from one specific service
docker compose logs -f decision-engine
docker compose logs -f api-gateway

# Restart a single service (e.g., after changing code)
docker compose restart api-gateway

# Check which services are running
docker compose ps

# Check resource usage
docker stats
```

---

<div align="center">

Built by [Aniketh](https://github.com/Aniketh-74)

*If this was useful or impressive, drop a ⭐ — it helps a lot*

</div>
