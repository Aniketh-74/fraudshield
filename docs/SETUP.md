# Setup Guide

Two paths to run the system: **Docker Compose** (recommended for development) and **Kubernetes/Kind** (production demo).

---

## Path A: Docker Compose

### Prerequisites

- Docker Desktop (with at least 4GB RAM allocated)
- `make` (pre-installed on macOS/Linux; Windows: use Git Bash or WSL)
- Python 3.11+ (for training only)

### Step 1: Train the ML Model

```bash
make train
```

This runs the LightGBM training pipeline (~5 minutes). Outputs to `training/models/`:
- `model.txt` — LightGBM native format (used by ml-scorer and shap-explainer)
- `calibrated_model.pkl` — sklearn wrapper with calibrated probabilities
- `feature_order.json` — feature names in exact order expected by model
- `category_mappings.json` — merchant category → integer encoding

> **Note:** `make train` uses a Docker container. You do not need Python installed locally.

### Step 2: Start All Services

```bash
make up
```

This starts all services via `docker compose up -d`. Services start in dependency order:
- Zookeeper → Kafka → kafka-init (creates topics)
- PostgreSQL → Redis
- feature-enrichment, ml-scorer, decision-engine, shap-explainer, api-gateway
- transaction-simulator (begins generating transactions automatically)
- dashboard (Nginx serving React build on port 3000)

### Step 3: Verify

```bash
# Check all services are running
docker compose ps

# Check API health
curl http://localhost:8000/health
# → {"status": "ok"}

# Check recent transactions (may take 30s for first decisions)
curl http://localhost:8000/api/transactions/recent
```

### Step 4: Open Dashboard

```
http://localhost:3000
```

You should see:
- Live feed updating with APPROVE/FLAG/BLOCK decisions
- Charts updating as transactions flow through
- India map showing transaction locations

### Common Operations

```bash
make logs          # Tail logs from all services
make stop          # Stop all containers (preserve volumes)
make clean         # Stop and remove containers + volumes
make train         # Re-train model (regenerates training/models/)
```

### Troubleshooting

**Live feed empty:**
Check Kafka consumer is running:
```bash
docker compose logs api-gateway | grep kafka_consumer
# Should see: kafka_consumer_started
```

**JSONB errors in recent transactions:**
Ensure `api-gateway` uses `db.create_pool()` not `asyncpg.create_pool()` directly (the former registers JSONB codec).

**Dashboard not loading:**
```bash
docker compose logs dashboard
# If "Module not found": run `cd dashboard && npm install && npm run build`
```

---

## Path B: Kubernetes / Kind

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (images built locally)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) v0.20+
- [kubectl](https://kubernetes.io/docs/tasks/tools/) v1.28+

### Step 1: Run Setup Script

```bash
bash setup-local.sh
```

This script (idempotent — safe to re-run):
1. Creates a Kind cluster named `fraud-detection` with ports 80/443 forwarded
2. Builds all 7 service Docker images via `docker compose build`
3. Loads images into Kind with `kind load docker-image`
4. Deploys ingress-nginx and waits for it to be ready
5. Deploys metrics-server (patched with `--kubelet-insecure-tls` for Kind HPA)
6. Applies all Kubernetes manifests in dependency order
7. Waits for all pods to reach Running state

Expected runtime: 5-10 minutes on first run (image builds + cluster creation).

### Step 2: Verify

```bash
# All pods should be Running
kubectl get pods -n fraud-detection

# Check API health via Ingress
curl http://localhost/api/health
# → {"status": "ok"}

# Check HPA (may show <unknown> until metrics-server stabilizes, ~2 min)
kubectl get hpa -n fraud-detection
```

### Step 3: Open Services

| Service | URL |
|---------|-----|
| Dashboard | http://localhost |
| API | http://localhost/api/health |
| Grafana | http://localhost:30300 (no login needed) |
| Prometheus | `kubectl port-forward svc/prometheus-service 9090:9090 -n fraud-detection` |

### Step 4: Run Load Test

```bash
# Install locust if not already installed
pip install locust

# Run 3-minute load test at 100 TPS
locust -f tests/load/locustfile.py --headless -u 100 -r 10 \
  --run-time 3m --host http://localhost/api-gateway \
  --html tests/load/report.html

# While running, watch HPA scale-up in another terminal:
kubectl get hpa -n fraud-detection -w
```

### Teardown

```bash
kind delete cluster --name fraud-detection
```

---

## Running Tests

### Unit Tests (no services needed)

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run unit tests (50 tests, ~1 second)
python -m pytest tests/unit/ -x -q
```

### Integration Tests (requires Docker for testcontainers)

```bash
# Spins real Postgres + Redis via Docker automatically
python -m pytest tests/integration/ -x -q
```

### Latency Test (requires ml-scorer running)

```bash
docker compose up ml-scorer -d
python -m pytest tests/integration/test_scorer_latency.py -v
```
