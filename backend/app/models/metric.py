"""
Model metrics history and model registry database model.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from datetime import datetime, timezone
from backend.app.database import Base

class ModelMetric(Base):
    __tablename__ = "model_metrics"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    algorithm = Column(String(100), nullable=False)
    precision = Column(Float, nullable=False)
    recall = Column(Float, nullable=False)
    f1_score = Column(Float, nullable=False)
    roc_auc = Column(Float, nullable=False)
    pr_auc = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False, default=0.5)
    confusion_matrix = Column(JSON, nullable=True)  # [[TN, FP], [FN, TP]]
    trained_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    dataset_rows = Column(Integer, nullable=True)
    is_active = Column(Integer, default=1)
    notes = Column(Text, nullable=True)
