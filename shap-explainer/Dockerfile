# shap-explainer/Dockerfile
# Stage 1: dependency builder
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: runtime
FROM python:3.11-slim AS runtime

# LightGBM requires libgomp1 for OpenMP multi-threading (same as ml-scorer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Non-root user (DOCK-02)
RUN adduser --disabled-password --gecos "" --uid 1001 appuser

WORKDIR /app

# Volume mount point for model artifacts (model.txt + feature_order.json)
# docker-compose mounts: ./training/models:/app/models:ro
RUN mkdir -p /app/models && chown appuser:appuser /app/models

COPY --chown=appuser:appuser config.py shap_computer.py db_handler.py main.py ./

USER appuser

# No EXPOSE (no HTTP endpoint — batch polling service)
# No HEALTHCHECK (batch job pattern; liveness checked via process supervision)

CMD ["python", "main.py"]
