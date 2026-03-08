"""
routes/metrics.py — Metrics and stats endpoints.

Routes:
    GET /api/metrics/summary   — aggregate metrics
    GET /api/stats/hourly      — per-hour decision counts for charting
"""
from fastapi import APIRouter, Request
from schemas import MetricsSummary, HourlyStat
import db

router = APIRouter()


@router.get("/metrics/summary", response_model=MetricsSummary)
async def get_metrics_summary(request: Request):
    """Return total_transactions, fraud_rate, blocked_count, avg_latency_ms, review_queue_count."""
    row = await db.get_metrics_summary(request.app.state.pool)
    return {
        "total_transactions": row["total_transactions"] or 0,
        "fraud_rate": float(row["fraud_rate"] or 0.0),
        "flagged_count": row["flagged_count"] or 0,
        "blocked_count": row["blocked_count"] or 0,
        "approved_count": row["approved_count"] or 0,
        "avg_latency_ms": float(row["avg_latency_ms"] or 0.0),
        "review_queue_count": row["review_queue_count"] or 0,
    }


@router.get("/stats/hourly", response_model=list[HourlyStat])
async def get_hourly_stats(request: Request):
    """Return per-hour decision counts for the last 24 hours."""
    rows = await db.get_hourly_stats(request.app.state.pool)
    return [
        {
            "hour": row["hour"].isoformat(),
            "decision": row["decision"],
            "count": row["count"],
        }
        for row in rows
    ]
