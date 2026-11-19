"""
Distributed Reliability & Degraded Mode Fail-Safe Test Suite for FraudShield 3.0 (Phase 5.1).
Forensically verifies:
1. Multi-worker concurrent idempotency (1 winner, N atomic rejections).
2. Circuit-breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
3. Degraded Feature Store Fail-Safe Policy ($500 and 0.150; $2,000 and 0.500 thresholds).
4. No silent approvals when feature store is degraded.
5. Reconciliation and recovery when Redis returns online.
"""

import time
import concurrent.futures
from datetime import datetime, timezone
import pytest

from backend.app.v3.schemas.canonical import CanonicalTransaction
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
from backend.app.v3.feature_store.redis_connection import RedisCircuitBreaker, CircuitState
from backend.app.v3.services.decision_engine import FraudDecisionEngine, DecisionAction, DecisionConfig


def make_canonical_tx(tx_id: str, amt: float, card_num: str = "4532015112830366") -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=datetime.now(timezone.utc),
        amount=amt,
        currency="USD",
        card_pan_token=f"tok_rel_{card_num[-4:]}_pci_dss",
        card_bin=card_num[:6],
        card_last4=card_num[-4:],
        card_network="VISA",
        card_type="CREDIT",
        merchant_id="merch_rel_001",
        mcc="5411",
        channel="ECOMMERCE"
    )


def test_multi_worker_concurrent_idempotency_simulation():
    """
    Simulates 16 concurrent submissions of an identical transaction ID across 4 simulated workers.
    Verifies that exactly 1 submission succeeds and 15 are atomically rejected as duplicates.
    """
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store, fallback_store=store)

    tx_id = f"tx_multiworker_{int(time.time()*1000)}"
    shared_tx = make_canonical_tx(tx_id, 125.0)

    def submit_worker(worker_id: int):
        return pipeline.enrich(shared_tx)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(submit_worker, i) for i in range(16)]
        results = [f.result() for f in futures]

    duplicates = sum(1 for r in results if r.is_duplicate)
    winners = sum(1 for r in results if not r.is_duplicate)

    assert winners == 1, f"Expected exactly 1 winner, found {winners}"
    assert duplicates == 15, f"Expected 15 duplicate rejections, found {duplicates}"


def test_degraded_mode_failsafe_escalation_policy():
    """
    Forensically validates the Degraded Feature Store Fail-Safe Policy:
    Threshold rules when is_degraded=True:
    1. amount >= $2,000 or p >= 0.50 -> MANUAL_REVIEW
    2. amount >= $500 or p >= 0.150 -> STEP_UP_2FA
    3. amount < $500 and p < 0.150 -> APPROVE (low-exposure only)
    Never silently approves non-trivial transactions during degraded operations.
    """
    decision_engine = FraudDecisionEngine()
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store, fallback_store=store)

    # 1. Low exposure ($45, p=0.04) in degraded mode -> APPROVE
    tx_low = make_canonical_tx("tx_deg_low", 45.0, card_num="4532015112830111")
    enr_low = pipeline.enrich(tx_low).model_copy(update={"is_degraded": True})
    dec_low = decision_engine.evaluate(fraud_probability=0.04, features=enr_low, optimal_threshold=0.700)
    assert dec_low.action == DecisionAction.APPROVE

    # 2. Medium amount ($650 >= $500, p=0.05) in degraded mode -> STEP_UP_2FA
    tx_mid = make_canonical_tx("tx_deg_mid", 650.0, card_num="4532015112830222")
    enr_mid = pipeline.enrich(tx_mid).model_copy(update={"is_degraded": True})
    dec_mid = decision_engine.evaluate(fraud_probability=0.05, features=enr_mid, optimal_threshold=0.700)
    assert dec_mid.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in dec_mid.rule_triggers
    assert any("degraded" in r.lower() for r in dec_mid.decision_reasons)

    # 3. Medium probability ($50, p=0.18 >= 0.150) in degraded mode -> STEP_UP_2FA
    tx_mid_p = make_canonical_tx("tx_deg_mid_p", 50.0, card_num="4532015112830333")
    enr_mid_p = pipeline.enrich(tx_mid_p).model_copy(update={"is_degraded": True})
    dec_mid_p = decision_engine.evaluate(fraud_probability=0.18, features=enr_mid_p, optimal_threshold=0.700)
    assert dec_mid_p.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in dec_mid_p.rule_triggers

    # 4. High amount ($2,500 >= $2,000, p=0.08) in degraded mode -> MANUAL_REVIEW
    tx_high = make_canonical_tx("tx_deg_high", 2500.0, card_num="4532015112830444")
    enr_high = pipeline.enrich(tx_high).model_copy(update={"is_degraded": True})
    dec_high = decision_engine.evaluate(fraud_probability=0.08, features=enr_high, optimal_threshold=0.700)
    assert dec_high.action == DecisionAction.MANUAL_REVIEW
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in dec_high.rule_triggers

    # 5. High probability ($100, p=0.55 >= 0.50) in degraded mode -> MANUAL_REVIEW
    tx_high_p = make_canonical_tx("tx_deg_high_p", 100.0, card_num="4532015112830555")
    enr_high_p = pipeline.enrich(tx_high_p).model_copy(update={"is_degraded": True})
    dec_high_p = decision_engine.evaluate(fraud_probability=0.55, features=enr_high_p, optimal_threshold=0.700)
    assert dec_high_p.action == DecisionAction.MANUAL_REVIEW


def test_circuit_breaker_transitions_and_recovery():
    """
    Verifies state transitions:
    CLOSED -> (3 failures) -> OPEN -> (cooldown elapsed) -> HALF_OPEN -> (success) -> CLOSED
    """
    cb = RedisCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    # 2 failures: remains CLOSED
    cb.record_failure(Exception("ConnErr 1"))
    cb.record_failure(Exception("ConnErr 2"))
    assert cb.state == CircuitState.CLOSED

    # 3rd failure: trips to OPEN
    cb.record_failure(Exception("ConnErr 3"))
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False  # Immediately fast-fails

    # Cooldown elapses
    time.sleep(0.12)
    assert cb.can_attempt() is True  # Probes in HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN

    # Recovery trial succeeds -> restores to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
