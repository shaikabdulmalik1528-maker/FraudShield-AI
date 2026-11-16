"""
Transaction database model.
Stores transaction features, risk metrics, and prediction classifications.
DOES NOT STORE REAL CARD NUMBERS, CVVs, OR CARDHOLDER PII.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, Text
from datetime import datetime, timezone
import uuid
from backend.app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(64), unique=True, index=True, default=lambda: f"TXN-{uuid.uuid4().hex[:12].upper()}")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    
    # Raw / Normalized transaction properties
    time_step = Column(Float, nullable=False)
    amount = Column(Float, nullable=False, index=True)
    features_json = Column(JSON, nullable=True)  # Stores V1 - V28 feature dictionary
    
    # Engine Outputs
    fraud_probability = Column(Float, nullable=False, index=True) # 0.0 to 1.0
    risk_score = Column(Float, nullable=False, index=True)        # 0.0 to 100.0
    risk_category = Column(String(20), nullable=False, index=True) # LOW, MEDIUM, HIGH
    prediction = Column(String(20), nullable=False, index=True)    # LEGITIMATE, SUSPICIOUS
    is_anomaly = Column(Boolean, nullable=False, default=False)
    anomaly_score = Column(Float, nullable=False, default=0.0)
    
    model_version = Column(String(50), default="1.0.0", nullable=False)
    explanation_json = Column(JSON, nullable=True)  # Stored SHAP explanation summary
    notes = Column(Text, nullable=True)
