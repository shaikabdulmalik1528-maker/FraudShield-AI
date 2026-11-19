"""
Unit tests for FraudShield Dual-Engine Router & Versioning Facade.
Verifies version resolution, heuristic payload detection, and non-interference.
"""

from backend.app.v3.services.dual_engine_router import DualEngineRouter, EngineVersion


def test_dual_engine_explicit_version_resolution():
    """Asserts that explicit version headers are strictly respected."""
    router = DualEngineRouter()
    assert router.resolve_version({}, explicit_version="1.0") == EngineVersion.V1_PCA
    assert router.resolve_version({}, explicit_version="v1") == EngineVersion.V1_PCA
    assert router.resolve_version({}, explicit_version="3.0") == EngineVersion.V3_CANONICAL
    assert router.resolve_version({}, explicit_version="v3") == EngineVersion.V3_CANONICAL


def test_dual_engine_legacy_pca_heuristic_detection():
    """Asserts that payloads containing the 30 PCA features route automatically to v1."""
    router = DualEngineRouter()

    # Legacy FraudShield 1.0 PCA payload
    legacy_payload = {"Time": 100.0, "Amount": 50.0}
    for i in range(1, 29):
        legacy_payload[f"V{i}"] = 0.0

    assert router.resolve_version(legacy_payload) == EngineVersion.V1_PCA


def test_dual_engine_canonical_v3_heuristic_detection():
    """Asserts that raw, ISO 8583, or IEEE-CIS payloads route to v3."""
    router = DualEngineRouter()

    # Modern ISO 8583 payload
    iso_payload = {"mti": "0100", "de2": "4532015112830366", "de4": 1000}
    assert router.resolve_version(iso_payload) == EngineVersion.V3_CANONICAL

    # IEEE-CIS payload
    ieee_payload = {"TransactionID": 1001, "TransactionAmt": 50.0, "TransactionDT": 1000}
    assert router.resolve_version(ieee_payload) == EngineVersion.V3_CANONICAL


def test_dual_engine_status_telemetry():
    """Verifies dual-engine operational telemetry and safety assertions."""
    router = DualEngineRouter()
    status = router.get_engine_status()

    assert status["v1_status"]["version"] == "1.0.0"
    assert status["v1_status"]["state"] == "FROZEN_PRESERVED"
    assert status["v1_status"]["quarantined_test_split_accessed"] is False
    assert status["v3_status"]["version"] == "3.0.0-dev"
    assert status["v3_status"]["state"] == "PHASE_1_FOUNDATION"
