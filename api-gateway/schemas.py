"""
schemas.py — Pydantic v2 response models for API Gateway.
"""
from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime


class TransactionSummary(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    fraud_probability: float
    risk_level: str
    decision: str
    fired_rules: list[Any]
    created_at: datetime
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None


class TransactionDetail(TransactionSummary):
    feature_vector: dict[str, Any]
    shap_values: list[Any]
    analyst_decision: Optional[str] = None
    analyst_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    processing_latency_ms: Optional[float] = None


class MetricsSummary(BaseModel):
    total_transactions: int
    fraud_rate: float
    flagged_count: int
    blocked_count: int
    approved_count: int
    avg_latency_ms: float
    review_queue_count: int


class HourlyStat(BaseModel):
    hour: str   # ISO datetime string
    decision: str
    count: int


class ReviewRequest(BaseModel):
    decision: str  # "CONFIRMED_FRAUD" | "FALSE_POSITIVE"
    analyst_id: str = "analyst-1"
