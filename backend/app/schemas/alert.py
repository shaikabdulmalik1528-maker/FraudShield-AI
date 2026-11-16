"""
Fraud Alert schemas for detection and acknowledgment.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class AlertUpdate(BaseModel):
    status: str = Field(..., pattern="^(PENDING|INVESTIGATING|RESOLVED|FALSE_POSITIVE)$")
    notes: Optional[str] = Field(None, max_length=500)

class AlertResponse(BaseModel):
    id: int
    transaction_id: str
    risk_score: float
    fraud_probability: float
    status: str
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

