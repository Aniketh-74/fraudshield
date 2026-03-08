"""
routes/transactions.py — Transaction endpoints.

Routes:
    GET /api/transactions/recent     — last 100 decisions
    GET /api/transactions/{id}       — full transaction detail
"""
from fastapi import APIRouter, HTTPException, Request, Query
from schemas import TransactionSummary, TransactionDetail
import db

router = APIRouter()


@router.get("/transactions/recent", response_model=list[TransactionSummary])
async def get_recent_transactions(request: Request, limit: int = Query(default=100, le=500)):
    """Return the last N decisions ordered newest first."""
    rows = await db.get_recent_transactions(request.app.state.pool, limit=limit)
    return rows


@router.get("/transactions/flagged", response_model=list[TransactionSummary])
async def get_flagged_transactions(request: Request):
    """Return FLAG transactions that have not yet been reviewed, newest first."""
    rows = await db.get_flagged_transactions(request.app.state.pool)
    return rows


@router.get("/transactions/{transaction_id}", response_model=TransactionDetail)
async def get_transaction(transaction_id: str, request: Request):
    """Return full transaction detail including shap_values and analyst_decision fields."""
    row = await db.get_transaction_by_id(request.app.state.pool, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
    return row
