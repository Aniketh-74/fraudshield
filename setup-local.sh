#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="fraud-detection"
NAMESPACE="fraud-detection"

echo "[1/7] Creating Kind cluster with port mappings..."
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "  Cluster '${CLUSTER_NAME}' already exists, skipping creation"
else
  kind create cluster --name "${CLUSTER_NAME}" --config kind-config.yaml
fi

echo "[2/7] Building Docker images..."
docker compose build

echo "[3/7] Loading custom images into Kind..."
SERVICES="transaction-simulator feature-enrichment ml-scorer decision-engine shap-explainer api-gateway dashboard"
for svc in $SERVICES; do
  IMAGE="fraud-detection/${svc}:latest"
  echo "  Loading ${IMAGE}..."
  kind load docker-image "${IMAGE}" --name "${CLUSTER_NAME}"
done

echo "[4/7] Deploying ingress-nginx..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo "[5/7] Deploying metrics-server and patching for Kind..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system \
  --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

echo "[6/7] Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets/
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/statefulsets/
kubectl apply -f k8s/services/internal/
kubectl apply -f k8s/services/external/
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/hpa/
kubectl apply -f k8s/pdb/
kubectl apply -f k8s/networkpolicy/
kubectl apply -f k8s/ingress/
kubectl apply -f k8s/cronjob/
kubectl apply -f k8s/monitoring/ 2>/dev/null || echo "  (monitoring stack not yet deployed)"

echo "[7/7] Waiting for all pods to be ready..."
kubectl wait --for=condition=ready pod --all -n "${NAMESPACE}" --timeout=300s

echo ""
echo "Setup complete!"
echo "  Dashboard:  http://localhost"
echo "  API:        http://localhost/api/health"
echo "  Grafana:    http://localhost:3000 (admin/admin)"
echo "  Prometheus: http://localhost:9090"
