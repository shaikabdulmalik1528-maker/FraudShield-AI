"""
Fraud Alert database model for tracking flagged transactions.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from datetime import datetime, timezone
from backend.app.database import Base

class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(64), index=True, nullable=False)
    risk_score = Column(Float, nullable=False)
    fraud_probability = Column(Float, nullable=False)
    status = Column(String(30), default="PENDING", index=True, nullable=False) # PENDING, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    acknowledged_by = Column(String(50), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
