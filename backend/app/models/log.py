"""
Prediction audit logging model.
Tracks request latencies, payload sizes, and debugging details.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime, timezone
from backend.app.database import Base

class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(64), index=True, nullable=True)
    endpoint = Column(String(100), nullable=False)
    status_code = Column(Integer, nullable=False, default=200)
    latency_ms = Column(Float, nullable=False)
    input_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    client_ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
