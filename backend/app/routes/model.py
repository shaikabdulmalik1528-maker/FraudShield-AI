"""
Model metadata and runtime configuration endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import json
from typing import Dict, Any

from backend.app.config import settings
from backend.app.services.fraud_engine import fraud_engine
from backend.app.services.auth_service import get_current_user
from backend.app.models.user import User

router = APIRouter(prefix="/model", tags=["Model Information"])

class ThresholdUpdate(BaseModel):
    threshold: float = Field(..., ge=0.01, le=0.99, description="New decision threshold (0.01 to 0.99)")

@router.get("/info")
def get_model_information():
    """Returns runtime model version, active threshold, and algorithm configuration."""
    if not fraud_engine.is_loaded:
        fraud_engine.load_artifacts()

    return {
        "status": "active" if fraud_engine.is_loaded else "uninitialized",
        "champion_algorithm": fraud_engine.metadata.get("algorithm", "XGBClassifier"),
        "champion_model": fraud_engine.metadata.get("champion_model", "XGBoost"),
        "version": fraud_engine.metadata.get("version", "1.0.0"),
        "active_threshold": fraud_engine.threshold,
        "risk_weights": {
            "fraud_weight": fraud_engine.fraud_weight,
            "anomaly_weight": fraud_engine.anomaly_weight
        },
        "risk_thresholds": {
            "low_threshold": fraud_engine.low_threshold,
            "high_threshold": fraud_engine.high_threshold
        },
        "is_synthetic": fraud_engine.metadata.get("is_synthetic", False),
        "trained_at": fraud_engine.metadata.get("trained_at", None),
        "dataset_rows": fraud_engine.metadata.get("dataset_rows", 283726)
    }

@router.post("/threshold")
def update_decision_threshold(
    payload: ThresholdUpdate,
    current_user: User = Depends(get_current_user)
):
    """Dynamically adjust decision threshold (Admin only)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can adjust the model decision threshold."
        )

    fraud_engine.threshold = payload.threshold
    # Persist change
    if settings.THRESHOLD_PATH.exists():
        try:
            with open(settings.THRESHOLD_PATH, "r") as f:
                data = json.load(f)
            data["optimal_threshold"] = payload.threshold
            with open(settings.THRESHOLD_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    return {
        "message": f"Decision threshold updated to {payload.threshold:.3f}",
        "new_threshold": payload.threshold
    }
