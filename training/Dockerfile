FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
# libgomp1 required by LightGBM for OpenMP threading — MUST NOT omit
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -s /bin/false -u 1001 -m trainer \
    && mkdir -p /home/trainer/.config/matplotlib \
    && chown -R trainer:trainer /home/trainer
COPY --from=builder /install /usr/local
COPY . /app
WORKDIR /app
ENV MPLCONFIGDIR=/home/trainer/.config/matplotlib
USER trainer
ENTRYPOINT ["python", "train.py"]
