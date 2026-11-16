"""
Health check and system status endpoints.
"""

from fastapi import APIRouter
from datetime import datetime, timezone
from backend.app.config import settings
from backend.app.services.fraud_engine import fraud_engine

router = APIRouter(tags=["Health"])

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "model_loaded": fraud_engine.is_loaded,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
