# ---- Builder Stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Non-root user (uid 1001 — consistent with other services)
RUN useradd -r -u 1001 -s /bin/false appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appuser config.py redis_client.py feature_computer.py kafka_consumer.py main.py ./

USER appuser

# HEALTHCHECK: verify process is alive (no HTTP endpoint — use process check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os, sys; sys.exit(0)" || exit 1

CMD ["python", "main.py"]
