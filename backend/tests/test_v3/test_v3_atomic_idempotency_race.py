"""
Unit and concurrency tests for FraudShield 3.0 Atomic Deduplication & Idempotency.
Verifies:
1. IDEMP-01: 31-day retention covering 30-day sliding window (day 8-30 replay prevention).
2. IDEMP-02: Merchant scoping preventing cross-merchant ID collision.
3. RACE-01: Multi-threaded concurrent duplicate requests handled atomically.
"""

import pytest
import concurrent.futures
from datetime import datetime, timezone, timedelta
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.redis_store import (
    RedisSlidingWindowStore,
    DEFAULT_IDEMPOTENCY_TTL_SECONDS
)
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
import fakeredis


def make_idemp_tx(
    tx_id: str,
    card_token: str,
    amount: float,
    dt: datetime,
    merchant_id: str = "merch_alpha"
) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=dt,
        amount=amount,
        currency="USD",
        card_pan_token=card_token,
        card_bin="453201",
        card_last4="0366",
        card_network=CardNetwork.VISA,
        card_type=CardType.CREDIT,
        merchant_id=merchant_id,
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP
    )


def test_idempotency_ttl_exceeds_30_day_window():
    """IDEMP-01: Asserts that default idempotency TTL is 31 days (> 30-day window)."""
    assert DEFAULT_IDEMPOTENCY_TTL_SECONDS == 31 * 86400
    assert DEFAULT_IDEMPOTENCY_TTL_SECONDS > 30 * 86400


def test_idempotency_replay_after_seven_days():
    """
    IDEMP-01: Asserts that an event replayed 14 days later is still detected as a duplicate
    in the 31-day retention registry, eliminating the old 7-day replay vulnerability.
    """
    store = InMemorySlidingWindowStore()
    t0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    tx = make_idemp_tx("tx_replay_14d", "tok_v3_idemp_card", 100.0, t0)

    # Day 1: Ingest transaction
    assert store.record_transaction(tx) is True

    # Day 14 (within 31-day window): Replay identical transaction
    t_replay = t0 + timedelta(days=14)
    tx_replayed = make_idemp_tx("tx_replay_14d", "tok_v3_idemp_card", 100.0, t_replay)

    assert store.is_duplicate_transaction(tx_replayed.transaction_id, merchant_id=tx_replayed.merchant_id) is True
    assert store.record_transaction(tx_replayed) is False


def test_merchant_scoped_idempotency_isolation():
    """
    IDEMP-02: Asserts that identical transaction_ids under DIFFERENT merchants
    do NOT collide, maintaining merchant isolation.
    """
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    store = RedisSlidingWindowStore(redis_client=fake_client, prefix="fs3_test_scope")

    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    tx_merch_a = make_idemp_tx("INV_001", "tok_v3_card_alpha_01", 50.0, t0, merchant_id="merch_amazon")
    tx_merch_b = make_idemp_tx("INV_001", "tok_v3_card_bravo_02", 75.0, t0, merchant_id="merch_walmart")

    # Merchant A records INV_001
    assert store.record_transaction(tx_merch_a) is True
    # Merchant B should also be allowed to record INV_001
    assert store.record_transaction(tx_merch_b) is True

    # Merchant A replaying INV_001 must be rejected
    assert store.record_transaction(tx_merch_a) is False


def test_atomic_deduplication_under_high_concurrency():
    """
    RACE-01: High-concurrency test simulating 10 concurrent worker threads
    submitting identical transaction payload at the exact same millisecond.
    Guarantees: Exactly 1 thread records as new, and 9 threads receive is_duplicate=True.
    """
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    store = RedisSlidingWindowStore(redis_client=fake_client, prefix="fs3_concurrency")
    pipeline = StreamingFeaturePipeline(feature_store=store)

    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    target_tx = make_idemp_tx("tx_concurrent_race_99", "tok_v3_race_card", 120.0, t0)

    results = []
    num_threads = 10

    def submit_tx():
        return pipeline.enrich(target_tx)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(submit_tx) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Count how many recorded as duplicate vs new
    duplicate_count = sum(1 for r in results if r.is_duplicate is True)
    new_count = sum(1 for r in results if r.is_duplicate is False)

    # Exactly 1 new record, exactly 9 duplicates
    assert new_count == 1
    assert duplicate_count == 9
