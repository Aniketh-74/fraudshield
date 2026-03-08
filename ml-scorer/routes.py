"""
routes.py — FastAPI route definitions and Pydantic request/response models.

Routes:
    POST /predict  — Fraud probability prediction
    GET  /health   — Liveness probe (SCORE-07)

Pydantic models:
    PredictRequest  — 14 feature fields (all float) + transaction_id + user_id
    PredictResponse — fraud_probability, risk_level, model_version

Note: predict() is a synchronous def (not async def). FastAPI automatically runs
sync routes in a thread pool — this is correct for CPU-bound sklearn inference.
Using async def would block the event loop (Research Pitfall 7).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from predictor import predict

log = structlog.get_logger(__name__)
router = APIRouter()

# Module-level reference to model state dict (set by main.py at startup)
_model_state: dict = {}


def set_model_state(state: dict) -> None:
    """Called once from main.py lifespan after model is loaded."""
    _model_state.update(state)


# --- Pydantic Models ---

class PredictRequest(BaseModel):
    """
    Input to POST /predict.

    transaction_id and user_id are pass-through (returned for correlation).
    All 14 feature fields are float (matching training/features.py FEATURE_COLS order).
    Missing any of the 14 features → 422 Unprocessable Entity (Pydantic validation).
    No fallback to default values — fail loudly (Research Pitfall avoidance).
    """
    transaction_id: str
    user_id: str
    # 14 features in feature_order.json order:
    txn_count_1h: float
    txn_count_6h: float
    txn_count_24h: float
    avg_amount_7d: float
    amount_deviation: float
    time_since_last_txn_seconds: float
    unique_merchants_24h: float
    max_amount_24h: float
    is_new_merchant: float
    hour_of_day: float
    is_weekend: float
    geo_distance_km: float
    geo_velocity_kmh: float
    merchant_category_enc: float


class PredictResponse(BaseModel):
    """
    Response from POST /predict.
    Matches SCORE-01 contract exactly.
    """
    fraud_probability: float
    risk_level: str       # "LOW" | "MEDIUM" | "HIGH"
    model_version: str


class HealthResponse(BaseModel):
    status: str           # "ok"
    model_loaded: bool


# --- Routes ---

@router.post("/predict", response_model=PredictResponse)
def predict_endpoint(request: PredictRequest) -> PredictResponse:
    """
    POST /predict — Fraud probability prediction endpoint.

    Accepts enriched transaction JSON (all 14 feature fields + transaction_id + user_id).
    Returns fraud_probability, risk_level, model_version.

    Latency SLA: <50ms p99 (SCORE-04). Expected actual p99: 5–15ms per Research.

    Errors:
        422: Missing required feature fields (Pydantic validation — automatic)
        503: Model not loaded (if called before startup completes — should not happen)
    """
    if not _model_state:
        log.error("predict_called_before_model_loaded")
        raise HTTPException(status_code=503, detail="Model not loaded")

    calibrated_model = _model_state["calibrated_model"]
    feature_order = _model_state["feature_order"]
    model_version = _model_state["model_version"]

    # Build feature dict from request (Pydantic model → dict, then filter to 14 features)
    feature_values = {
        "txn_count_1h": request.txn_count_1h,
        "txn_count_6h": request.txn_count_6h,
        "txn_count_24h": request.txn_count_24h,
        "avg_amount_7d": request.avg_amount_7d,
        "amount_deviation": request.amount_deviation,
        "time_since_last_txn_seconds": request.time_since_last_txn_seconds,
        "unique_merchants_24h": request.unique_merchants_24h,
        "max_amount_24h": request.max_amount_24h,
        "is_new_merchant": request.is_new_merchant,
        "hour_of_day": request.hour_of_day,
        "is_weekend": request.is_weekend,
        "geo_distance_km": request.geo_distance_km,
        "geo_velocity_kmh": request.geo_velocity_kmh,
        "merchant_category_enc": request.merchant_category_enc,
    }

    fraud_probability, risk_level = predict(calibrated_model, feature_order, feature_values)

    log.debug(
        "prediction_complete",
        transaction_id=request.transaction_id,
        user_id=request.user_id,
        fraud_probability=fraud_probability,
        risk_level=risk_level,
        model_version=model_version,
    )

    return PredictResponse(
        fraud_probability=fraud_probability,
        risk_level=risk_level,
        model_version=model_version,
    )


@router.get("/health", response_model=HealthResponse)
def health_endpoint() -> HealthResponse:
    """
    GET /health — Kubernetes liveness probe (SCORE-07).
    Returns {"status": "ok", "model_loaded": true} when model is loaded.
    Returns {"status": "ok", "model_loaded": false} during startup (before model load).
    HTTP 200 always — Kubernetes decides liveness from model_loaded field if needed.
    """
    return HealthResponse(
        status="ok",
        model_loaded=bool(_model_state),
    )
