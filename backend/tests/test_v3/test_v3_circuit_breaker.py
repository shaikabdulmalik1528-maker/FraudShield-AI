"""
Unit tests for Redis Connection Management & Circuit Breaker (RESIL-01).
Verifies state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED) and
seamless pipeline fallback to in-memory store upon connection failure.
"""

import time
import pytest
from datetime import datetime, timezone
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.redis_connection import (
    RedisCircuitBreaker,
    CircuitState,
    RedisManager
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline


class BrokenStoreMock:
    """Mock store that simulates broken network connections."""
    def is_duplicate_transaction(self, tx_id, merchant_id=None):
        raise ConnectionError("Simulated Redis Connection Refused")

    def record_transaction(self, tx):
        raise ConnectionError("Simulated Redis Connection Refused")

    def get_card_velocity_stats(self, *args, **kwargs):
        raise ConnectionError("Simulated Redis Connection Refused")

    def get_merchant_velocity_stats(self, *args, **kwargs):
        raise ConnectionError("Simulated Redis Connection Refused")

    def get_last_known_location(self, *args, **kwargs):
        raise ConnectionError("Simulated Redis Connection Refused")


def test_circuit_breaker_trips_to_open_after_threshold():
    """Asserts that 3 consecutive failures transition circuit breaker from CLOSED to OPEN."""
    cb = RedisCircuitBreaker(failure_threshold=3, cooldown_seconds=1.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    # 1st failure
    cb.record_failure(RuntimeError("error 1"))
    assert cb.state == CircuitState.CLOSED

    # 2nd failure
    cb.record_failure(RuntimeError("error 2"))
    assert cb.state == CircuitState.CLOSED

    # 3rd failure -> Trips to OPEN
    cb.record_failure(RuntimeError("error 3"))
    assert cb.state == CircuitState.OPEN
    # Immediately rejects attempts while OPEN
    assert cb.can_attempt() is False


def test_circuit_breaker_recovers_to_closed_after_cooldown():
    """Asserts that after cooldown, circuit probes HALF_OPEN and resets on success."""
    cb = RedisCircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

    # Trip to OPEN
    cb.record_failure(RuntimeError("err 1"))
    cb.record_failure(RuntimeError("err 2"))
    assert cb.state == CircuitState.OPEN

    # Wait for cooldown
    time.sleep(0.15)
    assert cb.can_attempt() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Report success
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_pipeline_graceful_failover_on_broken_store():
    """
    RESIL-01: Asserts that if primary store drops mid-stream, StreamingFeaturePipeline
    gracefully fails over to the fallback in-memory store without throwing an unhandled exception.
    """
    broken_primary = BrokenStoreMock()
    fallback_memory = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=broken_primary, fallback_store=fallback_memory)

    tx = CanonicalTransaction(
        transaction_id="tx_resil_01",
        timestamp=datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        amount=75.0,
        currency="USD",
        card_pan_token="tok_v3_resilient_card",
        card_bin="453201",
        card_last4="0366",
        card_network=CardNetwork.VISA,
        card_type=CardType.DEBIT,
        merchant_id="merch_resil",
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP
    )

    # Must complete successfully via fallback store
    feat = pipeline.enrich(tx)
    assert feat.transaction_id == "tx_resil_01"
    assert feat.is_duplicate is False
    assert feat.card_tx_count_1h == 0
