"""
main.py — FastAPI application entry point for ml-scorer service.

Startup (lifespan):
    1. Configure structlog (JSON output for Docker)
    2. Load model artifacts from MODEL_DIR via model_loader.load_model_artifacts()
    3. Store in module-level model_state dict (shared with routes.py via set_model_state)
    4. Set MODEL_VERSION_INFO Prometheus gauge to 1.0 for loaded version
    5. Yield (app is now serving)

Shutdown (lifespan teardown):
    6. Clear model_state dict

Routes mounted:
    POST /predict  — from routes.router
    GET  /health   — from routes.router
    GET  /metrics  — Prometheus ASGI app (prometheus_client.make_asgi_app())

uvicorn runner:
    Called via CMD in Dockerfile: uvicorn ml_scorer.main:app --host 0.0.0.0 --port 8000
    Or: python main.py (uses uvicorn.run() guard at bottom)
"""
import structlog
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from starlette.routing import Mount

import config
from model_loader import load_model_artifacts
from metrics import MODEL_VERSION_INFO
from routes import router, set_model_state

log = structlog.get_logger(__name__)

model_state: dict = {}


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager (replaces deprecated @app.on_event("startup")).
    Loads model artifacts once before any requests are served.
    Clears state on shutdown.
    """
    configure_logging()
    log.info("ml_scorer_starting", model_dir=config.MODEL_DIR)

    # Load model artifacts (blocking — intentional, happens before first request)
    artifacts = load_model_artifacts(config.MODEL_DIR)
    model_state.update(artifacts)
    set_model_state(model_state)

    # Set Prometheus model version info gauge
    MODEL_VERSION_INFO.labels(version=artifacts["model_version"]).set(1)

    log.info(
        "ml_scorer_ready",
        model_version=artifacts["model_version"],
        feature_count=len(artifacts["feature_order"]),
    )

    yield  # Application is now serving requests

    log.info("ml_scorer_shutting_down")
    model_state.clear()


# --- Build FastAPI application ---
app = FastAPI(
    title="ML Scorer",
    description="Fraud probability scoring service",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount Prometheus metrics endpoint at /metrics
# Using make_asgi_app() per Research section on Prometheus integration
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include prediction and health routes
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        workers=config.WORKERS,
        log_level=config.LOG_LEVEL.lower(),
    )
