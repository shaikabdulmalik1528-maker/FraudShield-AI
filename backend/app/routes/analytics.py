"""
Analytics, Performance Metrics, and Fraud Trend API endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from backend.app.database import get_db
from backend.app.schemas.analytics import OverviewStats, FraudTrendItem, RiskDistributionItem
from backend.app.services.analytics_service import (
    get_overview_statistics,
    get_fraud_trends,
    get_risk_distribution,
    get_model_performance
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/overview", response_model=OverviewStats)
def overview_metrics(db: Session = Depends(get_db)):
    """Summary KPI metrics for the dashboard header."""
    return get_overview_statistics(db)

@router.get("/fraud-trends", response_model=List[FraudTrendItem])
def fraud_trend_series(db: Session = Depends(get_db)):
    """Hourly/Daily aggregated fraud frequency and risk trends."""
    return get_fraud_trends(db)

@router.get("/risk-distribution", response_model=List[RiskDistributionItem])
def risk_breakdown(db: Session = Depends(get_db)):
    """Distribution across LOW, MEDIUM, and HIGH risk bands."""
    return get_risk_distribution(db)

@router.get("/model-performance")
def model_benchmark_report():
    """Authentic comparative benchmark statistics between ML algorithms."""
    return get_model_performance()
