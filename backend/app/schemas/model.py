"""
Model information and configuration schemas.
"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

class ModelInfoResponse(BaseModel):
    name: str
    algorithm: str
    version: str
    status: str
    is_trained: bool
    features_expected: List[str]
    threshold: float
    weights: Dict[str, float]
    created_at: Optional[datetime] = None
    artifact_details: Dict[str, Any]
