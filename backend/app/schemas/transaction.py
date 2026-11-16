"""
Transaction and Prediction input/output schemas.
Strictly adheres to Kaggle PCA feature format (Time, V1..V28, Amount)
No PAN, CVV, or PII is ever accepted or stored.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

class ShapFeatureContribution(BaseModel):
    feature: str
    feature_value: float
    shap_value: float
    contribution: str  # "Increases Risk" or "Decreases Risk"
    impact_pct: float
    description: str

class PredictionExplanation(BaseModel):
    base_value: float
    prediction_value: float
    top_features: List[ShapFeatureContribution]
    summary: str

class TransactionInput(BaseModel):
    Time: float = Field(..., description="Seconds elapsed since the first transaction", ge=0.0)
    Amount: float = Field(..., description="Transaction monetary amount", ge=0.0)
    V1: float = Field(..., description="PCA Component 1")
    V2: float = Field(..., description="PCA Component 2")
    V3: float = Field(..., description="PCA Component 3")
    V4: float = Field(..., description="PCA Component 4")
    V5: float = Field(..., description="PCA Component 5")
    V6: float = Field(..., description="PCA Component 6")
    V7: float = Field(..., description="PCA Component 7")
    V8: float = Field(..., description="PCA Component 8")
    V9: float = Field(..., description="PCA Component 9")
    V10: float = Field(..., description="PCA Component 10")
    V11: float = Field(..., description="PCA Component 11")
    V12: float = Field(..., description="PCA Component 12")
    V13: float = Field(..., description="PCA Component 13")
    V14: float = Field(..., description="PCA Component 14")
    V15: float = Field(..., description="PCA Component 15")
    V16: float = Field(..., description="PCA Component 16")
    V17: float = Field(..., description="PCA Component 17")
    V18: float = Field(..., description="PCA Component 18")
    V19: float = Field(..., description="PCA Component 19")
    V20: float = Field(..., description="PCA Component 20")
    V21: float = Field(..., description="PCA Component 21")
    V22: float = Field(..., description="PCA Component 22")
    V23: float = Field(..., description="PCA Component 23")
    V24: float = Field(..., description="PCA Component 24")
    V25: float = Field(..., description="PCA Component 25")
    V26: float = Field(..., description="PCA Component 26")
    V27: float = Field(..., description="PCA Component 27")
    V28: float = Field(..., description="PCA Component 28")
    
    # Optional metadata (Non-sensitive)
    notes: Optional[str] = Field(None, max_length=200)

class TransactionBatchInput(BaseModel):
    transactions: List[TransactionInput] = Field(..., min_length=1, max_length=100)

class PredictionOutput(BaseModel):
    transaction_id: str
    timestamp: datetime
    amount: float
    fraud_probability: float  # 0.0 to 1.0
    fraud_probability_pct: float  # 0.0 to 100.0%
    is_anomaly: bool
    anomaly_score: float
    risk_score: float  # 0.0 to 100.0
    risk_category: str  # LOW, MEDIUM, HIGH
    prediction: str  # LEGITIMATE, SUSPICIOUS
    model_version: str
    explanation: Optional[PredictionExplanation] = None

class TransactionResponse(BaseModel):
    id: int
    transaction_id: str
    timestamp: datetime
    amount: float
    time_step: float
    fraud_probability: float
    risk_score: float
    risk_category: str
    prediction: str
    is_anomaly: bool
    anomaly_score: float
    model_version: str
    features: Optional[Dict[str, float]] = None
    explanation: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class PaginatedTransactions(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[TransactionResponse]
