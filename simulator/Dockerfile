# Transaction Simulator — Multi-stage Docker build
#
# Stage 1 (builder): install Python dependencies into /install
# Stage 2 (runtime): copy installed packages + source; run as non-root appuser
#
# Build:  docker build -t fraud-simulator .
# Run:    docker run --env-file .env fraud-simulator

# ── Stage 1: Builder ──────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user (security requirement)
RUN useradd -r -u 1001 -s /bin/false appuser

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=appuser:appuser . .

# Create writable data directory for CSV output
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

# Health check: verify main.py process is running
# (simulator has no HTTP endpoint — process presence is the only health signal)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1

ENV PYTHONUNBUFFERED=1
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TOPIC=transactions
ENV TXN_RATE=10
ENV FRAUD_RATE=0.03
ENV DATA_OUTPUT_PATH=/app/data/transactions.csv

CMD ["python", "main.py"]
