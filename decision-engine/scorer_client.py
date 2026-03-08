"""
scorer_client.py — Synchronous HTTP client for ML Scorer POST /predict.

Class:
    ScorerClient — persistent httpx.Client, call predict() per transaction
"""
import httpx
import structlog

log = structlog.get_logger(__name__)

# The 14 feature fields the ML scorer expects (from ml-scorer/routes.py PredictRequest)
_SCORER_FEATURE_FIELDS = [
    "txn_count_1h", "txn_count_6h", "txn_count_24h",
    "avg_amount_7d", "amount_deviation", "time_since_last_txn_seconds",
    "unique_merchants_24h", "max_amount_24h", "is_new_merchant",
    "hour_of_day", "is_weekend", "geo_distance_km",
    "geo_velocity_kmh", "merchant_category_enc",
]

_FALLBACK_RESPONSE = {
    "fraud_probability": 0.0,
    "risk_level": "LOW",
    "model_version": "fallback",
    "_fallback": True,
}


class ScorerClient:
    def __init__(self, scorer_url: str) -> None:
        self._client = httpx.Client(
            base_url=scorer_url,
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0),
        )

    def predict(self, enriched_txn: dict) -> dict:
        """
        POST /predict with the 14 feature fields extracted from enriched_txn.
        Also includes transaction_id and user_id for scorer-side correlation logging.

        Returns scorer response dict on success:
            {"fraud_probability": float, "risk_level": str, "model_version": str}

        Returns _FALLBACK_RESPONSE on any network or HTTP error (fail-open).
        Caller should check response.get("_fallback") to detect fallback path.
        """
        payload = {
            "transaction_id": enriched_txn.get("transaction_id", ""),
            "user_id": enriched_txn.get("user_id", ""),
        }
        for field in _SCORER_FEATURE_FIELDS:
            payload[field] = float(enriched_txn.get(field, 0.0))

        try:
            response = self._client.post("/predict", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            log.warning(
                "scorer_request_error_fail_open",
                error=str(e),
                transaction_id=enriched_txn.get("transaction_id"),
            )
            return _FALLBACK_RESPONSE
        except httpx.HTTPStatusError as e:
            log.warning(
                "scorer_http_error_fail_open",
                status_code=e.response.status_code,
                transaction_id=enriched_txn.get("transaction_id"),
            )
            return _FALLBACK_RESPONSE

    def close(self) -> None:
        self._client.close()
