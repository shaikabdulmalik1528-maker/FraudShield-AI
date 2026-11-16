"""
Transaction persistence, alert triggering, and history retrieval service.
"""

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timezone
import uuid

from backend.app.models.transaction import Transaction
from backend.app.models.alert import FraudAlert
from backend.app.models.log import PredictionLog
from backend.app.schemas.transaction import TransactionInput
from backend.app.services.fraud_engine import fraud_engine
from backend.app.utils.logger import logger

def process_and_record_transaction(
    db: Session,
    txn_input: TransactionInput,
    client_ip: Optional[str] = None
) -> Dict[str, Any]:
    """
    Runs prediction via hybrid fraud engine, records transaction in database,
    triggers alerts if suspicious or high risk, and writes prediction log.
    """
    start_time = datetime.now()
    feature_dict = txn_input.model_dump()
    notes = feature_dict.pop("notes", None)

    # Generate prediction and SHAP explanation
    prediction_result = fraud_engine.predict_transaction(
        transaction_dict=feature_dict,
        generate_explanation=True
    )
    
    latency_ms = (datetime.now() - start_time).total_seconds() * 1000.0
    txn_id = f"FS-{uuid.uuid4().hex[:10].upper()}"

    # Extract PCA features subset for storage
    pca_subset = {f"V{i}": feature_dict[f"V{i}"] for i in range(1, 29)}

    # Persist transaction
    db_txn = Transaction(
        transaction_id=txn_id,
        timestamp=datetime.now(timezone.utc),
        time_step=float(feature_dict["Time"]),
        amount=float(feature_dict["Amount"]),
        features_json=pca_subset,
        fraud_probability=prediction_result["fraud_probability"],
        risk_score=prediction_result["risk_score"],
        risk_category=prediction_result["risk_category"],
        prediction=prediction_result["prediction"],
        is_anomaly=prediction_result["is_anomaly"],
        anomaly_score=prediction_result["anomaly_score"],
        model_version=prediction_result["model_version"],
        explanation_json=prediction_result["explanation"],
        notes=notes
    )
    db.add(db_txn)

    # If flagged as SUSPICIOUS or HIGH risk, automatically trigger fraud alert
    if prediction_result["prediction"] == "SUSPICIOUS" or prediction_result["risk_category"] == "HIGH":
        alert = FraudAlert(
            transaction_id=txn_id,
            risk_score=prediction_result["risk_score"],
            fraud_probability=prediction_result["fraud_probability"],
            status="PENDING",
            notes=f"Auto-generated alert by FraudShield AI engine ({prediction_result['risk_category']} risk)."
        )
        db.add(alert)

    # Persist audit log
    audit_log = PredictionLog(
        transaction_id=txn_id,
        endpoint="/api/v1/predict",
        status_code=200,
        latency_ms=round(latency_ms, 2),
        input_payload={"Amount": feature_dict["Amount"], "Time": feature_dict["Time"]},
        response_payload={
            "risk_score": prediction_result["risk_score"],
            "prediction": prediction_result["prediction"]
        },
        client_ip=client_ip
    )
    db.add(audit_log)

    db.commit()
    db.refresh(db_txn)

    response_payload = {
        "transaction_id": txn_id,
        "timestamp": db_txn.timestamp,
        "amount": db_txn.amount,
        "fraud_probability": prediction_result["fraud_probability"],
        "fraud_probability_pct": prediction_result["fraud_probability_pct"],
        "is_anomaly": prediction_result["is_anomaly"],
        "anomaly_score": prediction_result["anomaly_score"],
        "risk_score": prediction_result["risk_score"],
        "risk_category": prediction_result["risk_category"],
        "prediction": prediction_result["prediction"],
        "model_version": prediction_result["model_version"],
        "explanation": prediction_result["explanation"]
    }
    return response_payload

def get_paginated_transactions(
    db: Session,
    page: int = 1,
    page_size: int = 15,
    risk_category: Optional[str] = None,
    prediction: Optional[str] = None,
    search: Optional[str] = None
) -> Tuple[int, List[Transaction]]:
    """Query transactions with filtering and pagination."""
    query = db.query(Transaction)

    if risk_category:
        query = query.filter(Transaction.risk_category == risk_category.upper())
    if prediction:
        query = query.filter(Transaction.prediction == prediction.upper())
    if search:
        query = query.filter(Transaction.transaction_id.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(desc(Transaction.timestamp)).offset((page - 1) * page_size).limit(page_size).all()
    return total, items

def get_transaction_by_id(db: Session, txn_id: str) -> Optional[Transaction]:
    """Retrieve transaction by unique transaction_id."""
    return db.query(Transaction).filter(Transaction.transaction_id == txn_id).first()
