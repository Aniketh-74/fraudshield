# decision-engine/Dockerfile
# Stage 1: dependency builder
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: runtime
FROM python:3.11-slim AS runtime

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Non-root user (DOCK-02)
RUN adduser --disabled-password --gecos "" --uid 1001 appuser

WORKDIR /app

# Copy application source
COPY --chown=appuser:appuser config.py rules_engine.py scorer_client.py \
     db_writer.py ws_broadcaster.py kafka_consumer.py main.py ./

# Default rules config (overridden by docker-compose volume mount for production)
COPY --chown=appuser:appuser rules.yaml /app/rules.yaml

USER appuser

# WebSocket port
EXPOSE 8765

# Health check: verify all modules import successfully
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import config, rules_engine, scorer_client, db_writer, ws_broadcaster, kafka_consumer" \
    || exit 1

CMD ["python", "main.py"]
