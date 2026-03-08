"""
routes/review.py — Analyst review endpoint.

Routes:
    POST /api/transactions/{id}/review   — record analyst decision
"""
from fastapi import APIRouter, HTTPException, Request
from schemas import ReviewRequest
import db

router = APIRouter()

VALID_DECISIONS = {"CONFIRMED_FRAUD", "FALSE_POSITIVE"}


@router.post("/transactions/{transaction_id}/review")
async def review_transaction(transaction_id: str, body: ReviewRequest, request: Request):
    """Record analyst_decision, analyst_id, and reviewed_at in the decisions table."""
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision '{body.decision}'. Must be one of: {sorted(VALID_DECISIONS)}",
        )
    await db.record_review(
        request.app.state.pool,
        transaction_id,
        body.decision,
        body.analyst_id,
    )
    return {
        "status": "ok",
        "transaction_id": transaction_id,
        "analyst_decision": body.decision,
    }
