"""
ML Governance, Model Registry & Drift Monitoring Test Suite for FraudShield 3.0.
Verifies Population Stability Index (PSI), Kolmogorov-Smirnov tests, concept drift tracking,
model version registry, and atomic rollback workflows.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v3.monitoring.drift_detector import compute_psi, DriftDetector
from backend.app.v3.ml.registry import ModelRegistry, ModelVersionMetadata

client = TestClient(app)
ADMIN_HEADERS = {"X-API-Key": "fs3_admin_sec_key_2026_dev"}
ANALYST_HEADERS = {"X-API-Key": "fs3_analyst_ui_key_2026_dev"}


def test_psi_distribution_divergence_math():
    """Verifies PSI calculation for stable, moderate, and significant drift conditions."""
    np.random.seed(42)
    baseline = np.random.normal(loc=100.0, scale=20.0, size=1000)

    # 1. Identical distribution -> Stable (PSI near 0)
    same_dist = np.random.normal(loc=100.0, scale=20.0, size=1000)
    psi_stable, status_stable = compute_psi(baseline, same_dist)
    assert psi_stable < 0.10
    assert status_stable == "STABLE"

    # 2. Moderate shift -> Moderate drift
    moderate_shift = np.random.normal(loc=107.0, scale=22.0, size=1000)
    psi_mod, status_mod = compute_psi(baseline, moderate_shift)
    assert 0.05 <= psi_mod < 0.30

    # 3. Severe shift -> Significant drift
    severe_shift = np.random.normal(loc=150.0, scale=40.0, size=1000)
    psi_severe, status_severe = compute_psi(baseline, severe_shift)
    assert psi_severe >= 0.25
    assert status_severe == "SIGNIFICANT_DRIFT"


def test_concept_drift_fraud_rate_alerting():
    """Verifies concept drift alert when rolling fraud rate surges abnormally."""
    detector = DriftDetector()
    detector.baselines = {"target": {"fraud_rate": 0.035}}

    # 1. Normal streaming traffic: ~3.5% fraud
    for _ in range(965):
        detector.record_prediction(0.04)
    for _ in range(35):
        detector.record_prediction(0.85)

    rep_normal = detector.evaluate_prediction_drift(optimal_threshold=0.700)
    assert rep_normal["status"] == "STABLE"
    assert rep_normal["is_concept_drift"] is False

    # 2. Influx of high-risk transactions: fraud rate rises to 15%
    for _ in range(150):
        detector.record_prediction(0.92)

    rep_surge = detector.evaluate_prediction_drift(optimal_threshold=0.700)
    assert rep_surge["is_concept_drift"] is True
    assert rep_surge["status"] == "CONCEPT_DRIFT_ALERT"


def test_model_registry_atomic_rollback(tmp_path):
    """Verifies atomic model rollback between production version and rollback target."""
    reg_file = tmp_path / "model_registry.json"
    reg = ModelRegistry(registry_path=reg_file)

    assert reg.active_version == "3.0.0"
    assert reg.rollback_target == "3.0.0-rc1"

    # Roll back to RC1
    success, msg = reg.rollback()
    assert success is True
    assert reg.active_version == "3.0.0-rc1"
    assert reg.rollback_target == "3.0.0"

    # Roll back again (swap back to 3.0.0)
    success, msg = reg.rollback()
    assert success is True
    assert reg.active_version == "3.0.0"
    assert reg.rollback_target == "3.0.0-rc1"


def test_api_model_rollback_endpoint():
    """Verifies the POST /api/v3/model/rollback HTTP endpoint."""
    response = client.post("/api/v3/model/rollback", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ROLLED_BACK"
    assert "active_version" in data
    assert "rollback_target" in data

    # Restore active version back to 3.0.0
    client.post("/api/v3/model/rollback", headers=ADMIN_HEADERS)


def test_api_monitoring_drift_endpoint():
    """Verifies the GET /api/v3/monitoring/drift telemetry endpoint."""
    response = client.get("/api/v3/monitoring/drift", headers=ANALYST_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "prediction_drift" in data
    assert "feature_drifts" in data
