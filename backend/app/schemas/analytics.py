"""
Dashboard Analytics Pydantic schemas.
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class OverviewStats(BaseModel):
    total_transactions: int
    fraudulent_transactions: int
    legitimate_transactions: int
    fraud_rate_pct: float
    average_risk_score: float
    total_volume_usd: float
    fraud_volume_usd: float
    open_alerts: int
    model_version: str
    is_demo_data: bool = False

class FraudTrendItem(BaseModel):
    date_or_hour: str
    total_count: int
    fraud_count: int
    fraud_rate: float
    avg_risk: float

class RiskDistributionItem(BaseModel):
    category: str  # LOW, MEDIUM, HIGH
    count: int
    percentage: float

class ConfusionMatrixData(BaseModel):
    tn: int
    fp: int
    fn: int
    tp: int

class ModelPerformanceMetrics(BaseModel):
    model_name: str
    algorithm: str
    version: str
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    pr_auc: float
    threshold: float
    confusion_matrix: ConfusionMatrixData
    trained_at: datetime
    dataset_rows: int
    top_features: List[Dict[str, Any]]
