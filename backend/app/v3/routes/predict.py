"""
FraudShield 3.0 Real-Time REST Inference API (`/api/v3/predict`).
High-throughput, low-latency endpoints for raw payload adaptation, streaming enrichment,
LightGBM inference, multi-tier decision routing, RBAC authorization, and structured audit trails.
Strictly PCI-DSS aligned: zero storage or logging of cleartext PAN.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Header, Request, Depends, status
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.app.v3.services.engine_v3 import engine_v3
from backend.app.v3.security.config import ClientRole, ApiKeyMetadata
from backend.app.v3.security.auth import require_role
from backend.app.v3.security.rate_limiter import check_rate_limit
from backend.app.v3.security.audit_logger import audit_logger
from backend.app.v3.monitoring.drift_detector import drift_detector
from backend.app.v3.ml.registry import model_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3", tags=["FraudShield 3.0 Inference Engine"])

MAX_REQUEST_BYTES = 1024 * 1024  # 1 MB max payload size limit to prevent DOS


class PredictionResponseV3(BaseModel):
    transaction_id: str
    timestamp: str
    amount: float
    currency: str
    card_masked: str
    is_fraud: bool
    fraud_probability: float
    risk_score: float
    action: str
    decision_reasons: List[str] = Field(default_factory=list)
    rule_triggers: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    is_duplicate: bool
    is_degraded: bool = False
    features_imputed: List[str] = Field(default_factory=list)
    model_version: str
    features_used: int
    latency_ms: float
    feature_store_backend: str


class BatchPredictionRequestV3(BaseModel):
    transactions: List[Dict[str, Any]] = Field(..., min_length=1, max_length=100)


class BatchPredictionResponseV3(BaseModel):
    total_processed: int
    flagged_fraud_count: int
    action_counts: Dict[str, int]
    avg_latency_ms: float
    predictions: List[PredictionResponseV3]


@router.post(
    "/predict",
    response_model=PredictionResponseV3,
    status_code=status.HTTP_200_OK,
    summary="Real-time transaction risk scoring and decision policy evaluation"
)
async def predict_transaction(
    payload: Dict[str, Any],
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    client: ApiKeyMetadata = Depends(require_role([ClientRole.SERVICE, ClientRole.ANALYST, ClientRole.ADMIN, ClientRole.PARTNER])),
    _rate_guard: ApiKeyMetadata = Depends(check_rate_limit)
):
    """
    Ingests transaction payloads in ISO 8583, IEEE-CIS, or Generic JSON format.
    Requires SERVICE, ANALYST, or ADMIN role and passes rate limiter.
    Executes streaming feature enrichment, LightGBM inference, and multi-tier decision routing.
    """
    # 1. Enforce payload size limit
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload exceeds maximum allowed limit of {MAX_REQUEST_BYTES} bytes."
        )

    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty request payload.")

    # Override transaction_id if provided via standard idempotency header
    if idempotency_key and "transaction_id" not in payload:
        payload["transaction_id"] = idempotency_key

    try:
        result = await run_in_threadpool(engine_v3.predict_raw, payload)

        # Record decision to tamper-evident audit log
        await run_in_threadpool(audit_logger.log_transaction_decision, client.key_id, client.role.value, result)

        # Record for rolling drift detection
        drift_detector.record_prediction(
            fraud_prob=result["fraud_probability"],
            features_dict=result.get("evidence")
        )

        return PredictionResponseV3(**result)
    except ValueError as ve:
        logger.warning("Validation failure in predict_transaction: %s", ve)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as exc:
        logger.error("Unhandled error during scoring: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction scoring service temporarily unavailable."
        )


@router.post(
    "/batch-predict",
    response_model=BatchPredictionResponseV3,
    status_code=status.HTTP_200_OK,
    summary="High-throughput batch transaction scoring"
)
async def batch_predict_transactions(
    request_body: BatchPredictionRequestV3,
    client: ApiKeyMetadata = Depends(require_role([ClientRole.SERVICE, ClientRole.ANALYST, ClientRole.ADMIN, ClientRole.PARTNER])),
    _rate_guard: ApiKeyMetadata = Depends(check_rate_limit)
):
    """
    Scores up to 100 transactions in a single batch request with aggregate telemetry.
    Requires valid API key.
    """
    start_t = time.perf_counter()
    predictions: List[PredictionResponseV3] = []
    action_counts: Dict[str, int] = {}
    flagged_fraud = 0

    for item in request_body.transactions:
        try:
            res = engine_v3.predict_raw(item)
            p = PredictionResponseV3(**res)
            predictions.append(p)
            action_counts[p.action] = action_counts.get(p.action, 0) + 1
            if p.is_fraud:
                flagged_fraud += 1

            audit_logger.log_transaction_decision(client.key_id, client.role.value, res)
            drift_detector.record_prediction(res["fraud_probability"], res.get("evidence"))
        except Exception as exc:
            logger.warning("Skipping failed item in batch: %s", exc)

    total_time_ms = (time.perf_counter() - start_t) * 1000.0
    avg_lat = round(total_time_ms / max(len(predictions), 1), 2)

    return BatchPredictionResponseV3(
        total_processed=len(predictions),
        flagged_fraud_count=flagged_fraud,
        action_counts=action_counts,
        avg_latency_ms=avg_lat,
        predictions=predictions
    )


@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    summary="FraudShield 3.0 Operational & Dual-Engine Telemetry"
)
async def get_v3_status(
    client: ApiKeyMetadata = Depends(require_role([ClientRole.ANALYST, ClientRole.ADMIN, ClientRole.SERVICE]))
):
    """Returns model health, active manifest, Redis circuit breaker state, and dual-engine metrics."""
    status_data = engine_v3.get_status()
    status_data["client_authenticated"] = client.name
    status_data["client_role"] = client.role.value
    status_data["model_registry"] = model_registry.get_lineage()
    return status_data


@router.post(
    "/reload",
    status_code=status.HTTP_200_OK,
    summary="Hot-reload LightGBM and preprocessor artifacts"
)
async def reload_artifacts(
    client: ApiKeyMetadata = Depends(require_role([ClientRole.ADMIN]))
):
    """
    Reloads model weights, preprocessor state, and threshold configuration without service restart.
    Restricted strictly to ADMIN role.
    """
    success = engine_v3.load_artifacts()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to hot-reload artifacts from disk."
        )

    audit_logger.log_model_lifecycle(
        event_type="MODEL_RELOADED",
        client_id=client.key_id,
        model_version=engine_v3.manifest.get("model_version", "3.0.0"),
        details={"optimal_threshold": engine_v3.optimal_threshold}
    )

    return {
        "status": "RELOADED",
        "optimal_threshold": engine_v3.optimal_threshold,
        "features_loaded": len(engine_v3.model.feature_names_) if engine_v3.model else 0
    }


@router.post(
    "/model/rollback",
    status_code=status.HTTP_200_OK,
    summary="Atomically roll back active model to target version"
)
async def rollback_model(
    client: ApiKeyMetadata = Depends(require_role([ClientRole.ADMIN]))
):
    """
    Atomically swaps active model version with rollback target and reloads weights.
    Restricted strictly to ADMIN role.
    """
    success, msg = model_registry.rollback()
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    reload_success = engine_v3.load_artifacts()
    if not reload_success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Rollback initiated but reload failed.")

    audit_logger.log_model_lifecycle(
        event_type="MODEL_ROLLBACK",
        client_id=client.key_id,
        model_version=model_registry.active_version or "unknown",
        details={"rollback_message": msg}
    )

    return {
        "status": "ROLLED_BACK",
        "active_version": model_registry.active_version,
        "rollback_target": model_registry.rollback_target,
        "message": msg
    }


@router.get(
    "/monitoring/drift",
    status_code=status.HTTP_200_OK,
    summary="Retrieve streaming feature and concept drift diagnostics"
)
async def get_drift_report(
    client: ApiKeyMetadata = Depends(require_role([ClientRole.ANALYST, ClientRole.ADMIN]))
):
    """
    Returns Population Stability Index (PSI) and Kolmogorov-Smirnov statistics
    comparing streaming feature values against baseline distributions.
    """
    return drift_detector.get_full_report()
