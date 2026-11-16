"""
Real-Time Single and Batch Prediction Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List

from backend.app.database import get_db
from backend.app.schemas.transaction import (
    TransactionInput,
    TransactionBatchInput,
    PredictionOutput
)
from backend.app.services.transaction_service import process_and_record_transaction
from backend.app.utils.logger import logger

router = APIRouter(tags=["Inference & Prediction"])

@router.post("/predict", response_model=PredictionOutput, status_code=status.HTTP_200_OK)
def predict_single_transaction(
    txn: TransactionInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Evaluates a single transaction in real time:
    1. Validates inputs via Pydantic schema
    2. Scales Time & Amount using fitted RobustScaler
    3. Runs Supervised XGBoost inference
    4. Runs Unsupervised Isolation Forest anomaly scoring
    5. Calculates multi-factor risk score & category
    6. Generates local SHAP explanation
    7. Stores transaction in database & triggers alert if suspicious
    8. Returns structured JSON
    """
    client_ip = request.client.host if request.client else "unknown"
    try:
        result = process_and_record_transaction(db=db, txn_input=txn, client_ip=client_ip)
        return result
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference engine failure: {str(e)}"
        )

@router.post("/predict/batch", response_model=List[PredictionOutput], status_code=status.HTTP_200_OK)
def predict_batch_transactions(
    batch: TransactionBatchInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Evaluates a batch of transactions sequentially and persists results."""
    client_ip = request.client.host if request.client else "unknown"
    results = []
    for txn in batch.transactions:
        try:
            res = process_and_record_transaction(db=db, txn_input=txn, client_ip=client_ip)
            results.append(res)
        except Exception as e:
            logger.error(f"Error processing item in batch: {e}")
            continue
    return results
