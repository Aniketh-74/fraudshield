.PHONY: build up down generate-data generate-data-timed train test clean k8s-setup k8s-deploy help

# Default target: show help
help:
	@echo "Fraud Detection Pipeline -- Make Targets"
	@echo ""
	@echo "  build          Build all Docker images"
	@echo "  up             Start all services (background)"
	@echo "  down           Stop all services"
	@echo "  generate-data  Run simulator to populate CSV (requires Kafka running)"
	@echo "  train          Run ML training pipeline"
	@echo "  test           Run test suite"
	@echo "  clean          Stop services and remove volumes"
	@echo "  k8s-setup      Create Kubernetes namespace and base resources"
	@echo "  k8s-deploy     Apply all Kubernetes manifests"

# Build all service images
build:
	docker compose build

# Start all services in background
# Note: ml-scorer requires ./training/models to exist. Run 'make train' first.
up:
	docker compose up -d

# Stop all services (preserves volumes)
down:
	docker compose down

# Run simulator in data-generation mode (writes CSV to simulator_data volume).
# Note: simulator/main.py does not support --csv-only; Kafka must be running.
# Workflow: make up (infrastructure only) -> make generate-data -> make train -> make up (full)
# Alternative for offline CSV generation: run the simulator standalone with a local Kafka.
generate-data:
	docker compose run --rm transaction-simulator python main.py

# Run simulator for exactly 3 hours then stop automatically (~108,000 transactions)
generate-data-timed:
	docker compose run --rm transaction-simulator sh -c "timeout 10800 python main.py; exit 0"

# Run ML training pipeline (requires generate-data first)
# Uses the 'training' profile service which is excluded from normal 'up'
train:
	docker compose --profile training run --rm training python train.py

# Run test suite (stub -- Phase 6 will add real tests)
test:
	pytest tests/ -v 2>/dev/null || echo "No tests found. Phase 6 will add the test suite."

# Stop services and remove all volumes (full clean slate)
clean:
	docker compose down -v --remove-orphans

# Kubernetes: create namespace and base resources (Phase 6)
k8s-setup:
	kubectl apply -f k8s/namespace.yaml

# Kubernetes: deploy all manifests (Phase 6)
k8s-deploy:
	kubectl apply -f k8s/
