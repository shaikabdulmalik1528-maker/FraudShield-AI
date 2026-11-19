"""
FraudShield 3.0 Production Health & Readiness Probes.
Provides `/health/live` (liveness) and `/health/ready` (readiness) for Kubernetes / Docker container orchestrators.
"""

from fastapi import APIRouter, status, Response
from typing import Dict, Any
from backend.app.v3.services.engine_v3 import engine_v3
from backend.app.v3.security.auth import api_key_manager

router = APIRouter(tags=["Health & Readiness"])


@router.get(
    "/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe for container orchestrators"
)
async def liveness_probe():
    """Confirms the API process is running and event loop is responsive."""
    return {"status": "ALIVE", "service": "FraudShield-AI", "version": "3.0.0"}


@router.get(
    "/health/ready",
    summary="Readiness probe for traffic routing"
)
async def readiness_probe(response: Response):
    """
    Verifies model weights are loaded in memory and key manager is active.
    Returns 200 if ready to serve traffic; 503 if warming up or uninitialized.
    """
    is_model_ready = engine_v3.is_loaded and (engine_v3.model is not None)
    is_auth_ready = bool(api_key_manager._keys_by_id)
    feature_store_state = engine_v3.redis_manager.circuit_breaker.state

    is_ready = is_model_ready and is_auth_ready

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "NOT_READY"
    else:
        response.status_code = status.HTTP_200_OK
        status_text = "READY"

    return {
        "status": status_text,
        "model_loaded": is_model_ready,
        "auth_ready": is_auth_ready,
        "feature_store_circuit": feature_store_state,
        "degraded_mode": feature_store_state != "CLOSED"
    }


@router.get(
    "/health/sandbox",
    status_code=status.HTTP_200_OK,
    summary="Minimal sanitized health probe for partner sandbox connectivity"
)
async def partner_sandbox_health():
    """
    Sanitized connectivity probe for external partners and Base44 frontend.
    Returns minimal safe health status with zero internal infrastructure or admin details.
    """
    is_ready = engine_v3.is_loaded and (engine_v3.model is not None)
    return {
        "status": "HEALTHY" if is_ready else "INITIALIZING",
        "service": "FraudShield 3.0 Partner Sandbox",
        "environment": "sandbox"
    }


@router.get(
    "/api/v3/sandbox/health",
    status_code=status.HTTP_200_OK,
    summary="Minimal sanitized health probe under API v3 prefix"
)
async def partner_sandbox_api_health():
    """Alias for /health/sandbox under /api/v3 prefix."""
    return await partner_sandbox_health()
