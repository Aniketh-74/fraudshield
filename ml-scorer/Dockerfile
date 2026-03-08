# ---- Builder Stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV MODEL_DIR=/app/models
ENV PORT=8000
ENV HOST=0.0.0.0
ENV WORKERS=1

# libgomp1: required by LightGBM for OpenMP threading (DOCK-03)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (uid 1001 — consistent with other services)
RUN useradd -r -u 1001 -s /bin/false appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appuser config.py model_loader.py predictor.py routes.py metrics.py main.py ./

# Create models directory — populated by volume mount or COPY at build time
# In local dev: volume mount from training output dir
# In production: COPY model files here during build
RUN mkdir -p /app/models && chown appuser:appuser /app/models

# Copy model artifacts if present in build context (optional — can also use volume)
# COPY --chown=appuser:appuser models/calibrated_model.pkl /app/models/calibrated_model.pkl
# COPY --chown=appuser:appuser models/feature_order.json   /app/models/feature_order.json
# COPY --chown=appuser:appuser models/model.txt            /app/models/model.txt

USER appuser

EXPOSE 8000

# HEALTHCHECK: HTTP probe against /health endpoint (model must be loaded)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "main.py"]
