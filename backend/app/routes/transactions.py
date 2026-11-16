"""
Transaction history retrieval and explanation lookup endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import math

from backend.app.database import get_db
from backend.app.models.transaction import Transaction
from backend.app.schemas.transaction import TransactionResponse, PaginatedTransactions
from backend.app.services.transaction_service import get_paginated_transactions, get_transaction_by_id

router = APIRouter(tags=["Transactions"])

@router.get("/transactions", response_model=PaginatedTransactions)
def list_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Items per page"),
    risk_category: Optional[str] = Query(None, description="Filter by LOW, MEDIUM, HIGH"),
    prediction: Optional[str] = Query(None, description="Filter by LEGITIMATE, SUSPICIOUS"),
    search: Optional[str] = Query(None, description="Search by transaction ID"),
    db: Session = Depends(get_db)
):
    total, items = get_paginated_transactions(
        db=db,
        page=page,
        page_size=page_size,
        risk_category=risk_category,
        prediction=prediction,
        search=search
    )
    total_pages = max(1, math.ceil(total / page_size))

    # Format responses
    serialized_items = []
    for item in items:
        serialized_items.append(
            TransactionResponse(
                id=item.id,
                transaction_id=item.transaction_id,
                timestamp=item.timestamp,
                amount=item.amount,
                time_step=item.time_step,
                fraud_probability=item.fraud_probability,
                risk_score=item.risk_score,
                risk_category=item.risk_category,
                prediction=item.prediction,
                is_anomaly=item.is_anomaly,
                anomaly_score=item.anomaly_score,
                model_version=item.model_version,
                features=item.features_json,
                explanation=item.explanation_json
            )
        )

    return PaginatedTransactions(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=serialized_items
    )

@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_single_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = get_transaction_by_id(db, transaction_id)
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found."
        )
    return TransactionResponse(
        id=txn.id,
        transaction_id=txn.transaction_id,
        timestamp=txn.timestamp,
        amount=txn.amount,
        time_step=txn.time_step,
        fraud_probability=txn.fraud_probability,
        risk_score=txn.risk_score,
        risk_category=txn.risk_category,
        prediction=txn.prediction,
        is_anomaly=txn.is_anomaly,
        anomaly_score=txn.anomaly_score,
        model_version=txn.model_version,
        features=txn.features_json,
        explanation=txn.explanation_json
    )

@router.get("/explanations/{transaction_id}")
def get_transaction_explanation(transaction_id: str, db: Session = Depends(get_db)):
    txn = get_transaction_by_id(db, transaction_id)
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found."
        )
    if not txn.explanation_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No SHAP explanation stored for transaction '{transaction_id}'."
        )
    return {
        "transaction_id": txn.transaction_id,
        "amount": txn.amount,
        "risk_score": txn.risk_score,
        "prediction": txn.prediction,
        "explanation": txn.explanation_json
    }
