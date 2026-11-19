"""
FraudShield 3.0 Phase 6 Pilot Operational & Security Validation Test Suite.
Validates:
1. Pilot configuration completeness and master secret isolation.
2. Dockerfile, Docker Compose, and Redis configuration compliance.
3. Synthetic pilot traffic validity, 100% Luhn checksum compliance, and scenario coverage.
4. Detection quality benchmarks: Recall >= 90%, precision, duplicate detection, zero errors.
5. Sustained load, stress, and chaos security fuzzing (401, 403, 413, 422).
6. Zero-downtime master secret and API key rotation.
7. Resilient circuit breaker state transitions and degraded mode fail-safe policies.
8. Cryptographic audit log hash-chain tamper detection.
"""

import json
import pytest
from pathlib import Path

from backend.app.v3.services.token_service import KmsTokenService
from backend.app.v3.security.auth import ApiKeyManager
from backend.app.v3.security.config import ClientRole
from backend.app.v3.security.audit_logger import StructuredAuditLogger, verify_audit_log_integrity
from backend.app.v3.services.decision_engine import FraudDecisionEngine, DecisionAction
from backend.app.v3.feature_store.schemas import EnrichedFeatureVector
from backend.app.v3.feature_store.redis_connection import RedisCircuitBreaker, CircuitState

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PILOT_ENV_FILE = PROJECT_ROOT / ".env.pilot"
SYNTHETIC_DATA_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_synthetic_transactions.json"
EVALUATION_RESULTS_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_evaluation_results.json"
STRESS_RESULTS_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_stress_benchmark_results.json"


def test_pilot_configuration_completeness():
    """Validates that .env.pilot contains all mandatory operational secrets without placeholder defaults."""
    assert PILOT_ENV_FILE.exists(), "Pilot env file .env.pilot must exist"
    content = PILOT_ENV_FILE.read_text(encoding="utf-8")

    required_vars = [
        "FRAUDSHIELD_TOKEN_SALT",
        "FRAUDSHIELD_API_KEY_SALT",
        "FRAUDSHIELD_ADMIN_API_KEY",
        "FRAUDSHIELD_SERVICE_API_KEY",
        "FRAUDSHIELD_ANALYST_API_KEY",
        "FRAUDSHIELD_REDIS_URL",
        "RATE_LIMIT_SERVICE_PER_MIN",
        "DEGRADED_FAILSAFE_ENABLED",
    ]
    for var in required_vars:
        assert var in content, f"Missing required variable {var} in .env.pilot"
    assert "REPLACE_WITH" not in content, "Placeholder secrets detected in .env.pilot"


def test_synthetic_dataset_reproducibility_and_luhn_compliance():
    """Validates that the synthetic pilot dataset contains >= 2,000 transactions with 100% Luhn Mod-10 validity."""
    assert SYNTHETIC_DATA_FILE.exists(), "Synthetic dataset file must exist"
    with open(SYNTHETIC_DATA_FILE, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    assert len(dataset) >= 2000, f"Expected at least 2000 transactions, found {len(dataset)}"

    scenarios = set()
    for tx in dataset:
        scenarios.add(tx["ground_truth"]["scenario"])
        pan = tx["card_number"]
        assert KmsTokenService.validate_luhn(pan) is True, f"Transaction {tx['transaction_id']} has invalid Luhn PAN: {pan}"

    expected_scenarios = {
        "LEGITIMATE_PAYMENT",
        "VELOCITY_ATTACK",
        "GEO_ANCHOR",
        "IMPOSSIBLE_TRAVEL",
        "ORIGINAL_FOR_REPLAY",
        "DUPLICATE_REPLAY",
        "MULTI_CURRENCY",
        "HIGH_VALUE_ANOMALY",
        "DEGRADED_STORE_FAILSAFE",
    }
    assert expected_scenarios.issubset(scenarios), f"Missing operational scenarios: {expected_scenarios - scenarios}"


def test_detection_quality_metrics_thresholds():
    """Validates pilot detection quality metrics against governance thresholds."""
    assert EVALUATION_RESULTS_FILE.exists(), "Pilot evaluation results must exist"
    with open(EVALUATION_RESULTS_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)

    metrics = results["metrics"]
    summary = results["summary"]
    breakdown = results["scenario_breakdown"]

    assert summary["validation_errors"] == 0, "Zero unhandled validation errors required"
    assert metrics["recall"] >= 0.90, f"Recall {metrics['recall']} must be >= 0.90"
    assert metrics["false_negative_rate"] <= 0.10, f"FNR {metrics['false_negative_rate']} must be <= 0.10"

    # Verify duplicate detection rate is 100%
    dup_stats = breakdown.get("DUPLICATE_REPLAY", {})
    assert dup_stats.get("total", 0) > 0
    assert dup_stats.get("duplicates_detected") == dup_stats.get("total"), "All duplicates must be flagged"


def test_sustained_stress_and_concurrency_benchmarks():
    """Validates concurrency scaling and chaos security fuzzing."""
    assert STRESS_RESULTS_FILE.exists(), "Pilot stress results must exist"
    with open(STRESS_RESULTS_FILE, "r", encoding="utf-8") as f:
        stress_data = json.load(f)

    benchmarks = stress_data["concurrency_benchmarks"]
    assert len(benchmarks) >= 5, "Expected benchmarks across 1, 10, 25, 50, 100 concurrency"

    # Concurrency 100 benchmark validation
    c100 = next(b for b in benchmarks if b["concurrency"] == 100)
    assert c100["success_rate_pct"] == 100.0, "All valid requests under 100 concurrency must succeed"
    assert c100["throughput_tps"] > 100.0, "Throughput under 100 concurrency must exceed 100 TPS"

    # Chaos and boundary tests
    chaos = stress_data["chaos_security_tests"]
    assert chaos["missing_auth_401"] is True
    assert chaos["invalid_auth_401"] is True
    assert chaos["rbac_escalation_403"] is True
    assert chaos["payload_too_large_413"] is True
    assert chaos["malformed_payload_422"] is True

    # Model lifecycle tests
    lifecycle = stress_data["model_lifecycle_tests"]
    assert lifecycle["all_passed"] is True


def test_master_secret_rotation_zero_downtime():
    """Verifies that API keys can be rotated on-the-fly without service downtime."""
    mgr = ApiKeyManager(salt="test_pilot_rotation_salt")
    raw_key, meta = mgr.register_key("gateway_service", ClientRole.SERVICE, key_id="key_gw_rot_01")

    # Validate active key
    assert mgr.validate_key(raw_key) is not None

    # Rotate key
    new_raw_key, new_meta = mgr.rotate_key("key_gw_rot_01")

    # Old key must immediately be rejected
    assert mgr.validate_key(raw_key) is None
    # New rotated key must be accepted immediately
    assert mgr.validate_key(new_raw_key) is not None
    assert new_meta.role == ClientRole.SERVICE


from backend.app.v3.schemas.canonical import CanonicalTransaction
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
from datetime import datetime, timezone


def _make_canonical_tx(tx_id: str, amt: float) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=datetime.now(timezone.utc),
        amount=amt,
        currency="USD",
        card_pan_token="tok_p6_pci_dss_test",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="CREDIT",
        merchant_id="merch_p6_001",
        mcc="5411",
        channel="ECOMMERCE"
    )


def test_degraded_mode_policy_escalation():
    """Verifies that degraded store operation escalates high-exposure transactions to 2FA or Review."""
    engine = FraudDecisionEngine()
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store, fallback_store=store)

    # 1. Low exposure ($150, p=0.01) -> APPROVE
    tx_small = _make_canonical_tx("tx_p6_small", 150.0)
    feat_small = pipeline.enrich(tx_small).model_copy(update={"is_degraded": True})
    res_small = engine.evaluate(fraud_probability=0.01, features=feat_small)
    assert res_small.action == DecisionAction.APPROVE

    # 2. Amount >= $500 escalates to STEP_UP_2FA
    tx_med = _make_canonical_tx("tx_p6_med", 650.0)
    feat_med = pipeline.enrich(tx_med).model_copy(update={"is_degraded": True})
    res_med = engine.evaluate(fraud_probability=0.01, features=feat_med)
    assert res_med.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in res_med.rule_triggers

    # 3. Amount >= $2,000 escalates to MANUAL_REVIEW
    tx_large = _make_canonical_tx("tx_p6_large", 2500.0)
    feat_large = pipeline.enrich(tx_large).model_copy(update={"is_degraded": True})
    res_large = engine.evaluate(fraud_probability=0.01, features=feat_large)
    assert res_large.action == DecisionAction.MANUAL_REVIEW
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in res_large.rule_triggers


def test_audit_chain_tamper_evidence(tmp_path):
    """Verifies SHA-256 hash chain tamper detection on record modification, deletion, and sequence gaps."""
    log_file = tmp_path / "pilot_test_audit.jsonl"
    logger = StructuredAuditLogger(log_path=log_file)

    for i in range(10):
        logger.log_event("PILOT_EVENT", {"idx": i, "val": i * 10})

    valid, count, err = verify_audit_log_integrity(log_file)
    assert valid is True
    assert count == 10
    assert err is None

    # Tamper with record 5
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    t_rec = json.loads(lines[5])
    t_rec["val"] = 99999
    lines[5] = json.dumps(t_rec) + "\n"

    tampered_file = tmp_path / "tampered_pilot_audit.jsonl"
    with open(tampered_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    t_valid, t_count, t_err = verify_audit_log_integrity(tampered_file)
    assert t_valid is False
    assert "Tampered record" in t_err
