"""
Distributed Reliability & Fail-Safe Test Suite for FraudShield 3.0.
Verifies multi-worker concurrency, Redis failure injection, circuit-breaker transitions,
split-brain in-memory divergence, fail-safe non-approval enforcement, and Redis reconciliation.
"""

import time
import concurrent.futures
from datetime import datetime, timezone
import pytest

from backend.app.v3.schemas.canonical import CanonicalTransaction, PaymentChannel
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
from backend.app.v3.feature_store.redis_connection import RedisCircuitBreaker
from backend.app.v3.services.decision_engine import FraudDecisionEngine, DecisionConfig, DecisionAction


def make_test_tx(tx_id: str, amount: float = 100.0, card_token: str = "tok_dist_card_001") -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=datetime.now(timezone.utc),
        amount=amount,
        currency="USD",
        card_pan_token=card_token,
        card_bin="453201",
        card_last4="1234",
        card_network="VISA",
        card_type="DEBIT",
        merchant_id="merch_dist_01",
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.ECOMMERCE
    )


def test_concurrent_transactions_across_workers():
    """
    Simulates 8 concurrent worker threads submitting identical transaction IDs
    against a shared pipeline. Exactly 1 must record; 7 must be flagged as duplicates.
    """
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store)

    tx = make_test_tx("tx_concurrent_dist_001", amount=120.0)

    def worker_submit():
        return pipeline.enrich(tx)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_submit) for _ in range(8)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    duplicates = [r for r in results if r.is_duplicate]
    successes = [r for r in results if not r.is_duplicate]

    assert len(successes) == 1, "Exactly one transaction should succeed in race condition"
    assert len(duplicates) == 7, "Remaining 7 transactions must be atomically flagged as duplicates"


def test_circuit_breaker_complete_state_lifecycle():
    """
    Verifies state transitions: CLOSED -> OPEN (after 3 failures) -> HALF_OPEN (after cooldown) -> CLOSED (after probe).
    """
    cb = RedisCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)

    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # 1. Trigger 2 failures (under threshold)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # 2. Trigger 3rd failure (trips circuit)
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # 3. Wait for cooldown
    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # 4. Successful probe closes circuit
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True


def test_degraded_store_failsafe_policy_prevents_silent_approval():
    """
    Simulates two independent worker processes with uncoordinated in-memory stores (split-brain).
    Verifies that the Fail-Safe Policy intercepts transactions and refuses automated APPROVE.
    """
    # Worker A store
    store_a = InMemorySlidingWindowStore()
    pipe_a = StreamingFeaturePipeline(feature_store=store_a, fallback_store=store_a)

    # Worker B store (divergent local memory)
    store_b = InMemorySlidingWindowStore()
    pipe_b = StreamingFeaturePipeline(feature_store=store_b, fallback_store=store_b)

    decision_engine = FraudDecisionEngine(
        config=DecisionConfig(
            degraded_amount_threshold=500.0,
            degraded_prob_threshold=0.150,
            degraded_failsafe_enabled=True
        )
    )

    # Transaction 1: Worker A processes high amount ($750.00) with low probability (p=0.05)
    tx_high_amount = make_test_tx("tx_failsafe_001", amount=750.0)
    enriched_a = pipe_a.enrich(tx_high_amount)

    assert enriched_a.is_degraded is True

    decision_a = decision_engine.evaluate(
        fraud_probability=0.05,
        features=enriched_a,
        optimal_threshold=0.700
    )

    # MUST NOT be silently approved! Must escalate to STEP_UP_2FA due to degraded mode
    assert decision_a.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in decision_a.rule_triggers
    assert any("degraded feature store" in r.lower() for r in decision_a.decision_reasons)

    # Transaction 2: Worker B processes high risk (p=0.20) with modest amount ($100.00)
    tx_modest = make_test_tx("tx_failsafe_002", amount=100.0)
    enriched_b = pipe_b.enrich(tx_modest)

    decision_b = decision_engine.evaluate(
        fraud_probability=0.20,
        features=enriched_b,
        optimal_threshold=0.700
    )

    # MUST NOT be approved! Must escalate to STEP_UP_2FA because p >= 0.150
    assert decision_b.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in decision_b.rule_triggers

    # Transaction 3: Very high exposure ($2500.00) during degradation escalates to MANUAL_REVIEW
    tx_whale = make_test_tx("tx_failsafe_003", amount=2500.0)
    enriched_whale = pipe_b.enrich(tx_whale)

    decision_whale = decision_engine.evaluate(
        fraud_probability=0.05,
        features=enriched_whale,
        optimal_threshold=0.700
    )

    assert decision_whale.action == DecisionAction.MANUAL_REVIEW
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in decision_whale.rule_triggers


def test_graceful_failover_when_primary_store_crashes():
    """
    Simulates a primary store raising runtime exceptions mid-flight.
    Verifies that the pipeline seamlessly falls back without crashing or throwing unhandled exceptions.
    """
    class CrashingStore(InMemorySlidingWindowStore):
        def get_card_velocity_stats(self, *args, **kwargs):
            raise ConnectionError("Redis cluster connection severed mid-flight!")

    crashing_store = CrashingStore()
    backup_store = InMemorySlidingWindowStore()

    pipe = StreamingFeaturePipeline(feature_store=crashing_store, fallback_store=backup_store)
    tx = make_test_tx("tx_crash_sim_001", amount=50.0)

    # Must complete safely via fallback
    enriched = pipe.enrich(tx)
    assert enriched.transaction_id == "tx_crash_sim_001"
    assert enriched.is_degraded is True
    assert "card_velocity" in enriched.features_imputed
