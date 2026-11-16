"""
Analytics and Dashboard Data Service.
Computes real-time statistics, fraud trends, risk distributions, and model performance.
"""

import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timezone, timedelta

from backend.app.models.transaction import Transaction
from backend.app.models.alert import FraudAlert
from backend.app.schemas.analytics import OverviewStats, FraudTrendItem, RiskDistributionItem
from backend.app.config import settings

def get_overview_statistics(db: Session) -> Dict[str, Any]:
    """Computes high-level KPI card metrics strictly from real transaction data."""
    total_txns = db.query(func.count(Transaction.id)).scalar() or 0
    fraud_txns = db.query(func.count(Transaction.id)).filter(Transaction.prediction == "SUSPICIOUS").scalar() or 0
    legit_txns = total_txns - fraud_txns
    
    fraud_rate = (fraud_txns / total_txns * 100.0) if total_txns > 0 else 0.0
    avg_risk = db.query(func.avg(Transaction.risk_score)).scalar() or 0.0
    total_vol = db.query(func.sum(Transaction.amount)).scalar() or 0.0
    fraud_vol = db.query(func.sum(Transaction.amount)).filter(Transaction.prediction == "SUSPICIOUS").scalar() or 0.0
    open_alerts = db.query(func.count(FraudAlert.id)).filter(FraudAlert.status == "PENDING").scalar() or 0

    version = "1.0.0"
    if settings.METRICS_PATH.exists():
        try:
            with open(settings.METRICS_PATH, "r") as f:
                meta = json.load(f)
                version = meta.get("version", "1.0.0")
        except Exception:
            pass

    return {
        "total_transactions": total_txns,
        "fraudulent_transactions": fraud_txns,
        "legitimate_transactions": legit_txns,
        "fraud_rate_pct": round(fraud_rate, 2),
        "average_risk_score": round(float(avg_risk), 1),
        "total_volume_usd": round(float(total_vol), 2),
        "fraud_volume_usd": round(float(fraud_vol), 2),
        "open_alerts": open_alerts,
        "model_version": version,
        "is_demo_data": False
    }

def get_fraud_trends(db: Session, limit_hours: int = 24) -> List[Dict[str, Any]]:
    """
    Computes time-series trend of transaction activity and fraud occurrences.
    """
    # Group recent transactions into time buckets
    txns = db.query(Transaction).order_by(Transaction.timestamp.asc()).all()
    if not txns:
        return []

    # Aggregate by hour/day
    buckets: Dict[str, Dict[str, Any]] = {}
    for txn in txns:
        bucket_key = txn.timestamp.strftime("%Y-%m-%d %H:00")
        if bucket_key not in buckets:
            buckets[bucket_key] = {"total": 0, "fraud": 0, "risk_sum": 0.0}
        buckets[bucket_key]["total"] += 1
        if txn.prediction == "SUSPICIOUS":
            buckets[bucket_key]["fraud"] += 1
        buckets[bucket_key]["risk_sum"] += txn.risk_score

    trend_items = []
    for key, data in sorted(buckets.items()):
        total = data["total"]
        fraud = data["fraud"]
        avg_risk = data["risk_sum"] / total if total > 0 else 0.0
        fraud_rate = (fraud / total * 100.0) if total > 0 else 0.0
        trend_items.append({
            "date_or_hour": key,
            "total_count": total,
            "fraud_count": fraud,
            "fraud_rate": round(fraud_rate, 2),
            "avg_risk": round(avg_risk, 1)
        })

    return trend_items[-24:] # Return last 24 periods

def get_risk_distribution(db: Session) -> List[Dict[str, Any]]:
    """Calculates distribution count and percentage across LOW, MEDIUM, and HIGH risk."""
    total = db.query(func.count(Transaction.id)).scalar() or 0
    if total == 0:
        return [
            {"category": "LOW", "count": 0, "percentage": 0.0},
            {"category": "MEDIUM", "count": 0, "percentage": 0.0},
            {"category": "HIGH", "count": 0, "percentage": 0.0},
        ]

    low_count = db.query(func.count(Transaction.id)).filter(Transaction.risk_category == "LOW").scalar() or 0
    med_count = db.query(func.count(Transaction.id)).filter(Transaction.risk_category == "MEDIUM").scalar() or 0
    high_count = db.query(func.count(Transaction.id)).filter(Transaction.risk_category == "HIGH").scalar() or 0

    return [
        {"category": "LOW", "count": low_count, "percentage": round((low_count / total) * 100.0, 1)},
        {"category": "MEDIUM", "count": med_count, "percentage": round((med_count / total) * 100.0, 1)},
        {"category": "HIGH", "count": high_count, "percentage": round((high_count / total) * 100.0, 1)},
    ]

def get_model_performance() -> Dict[str, Any]:
    """Reads real trained benchmark metrics and feature importance from model_metrics.json."""
    if not settings.METRICS_PATH.exists():
        return {
            "status": "not_trained",
            "message": "Model training has not been executed yet. Train model to view authentic metrics."
        }
    with open(settings.METRICS_PATH, "r") as f:
        data = json.load(f)
    return data
