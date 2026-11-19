"""
Unit tests for FraudShield 3.0 Sliding Window Velocity Aggregations.
Verifies 1h, 24h, 7d, 30d windows, spend sums, baseline ratios, and merchant metrics.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore


def make_test_tx(
    tx_id: str,
    card_token: str,
    amount: float,
    dt: datetime,
    merchant_id: str = "merch_target_001",
    channel: PaymentChannel = PaymentChannel.POS_CHIP
) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=dt,
        amount=amount,
        currency="USD",
        card_pan_token=card_token,
        card_bin="411111",
        card_last4="1111",
        card_network=CardNetwork.VISA,
        card_type=CardType.DEBIT,
        merchant_id=merchant_id,
        mcc="5411",
        merchant_country="USA",
        channel=channel
    )


def test_card_velocity_sliding_windows():
    """
    Asserts that 1h, 24h, 7d, and 30d sliding windows correctly segment transactions.
    """
    store = InMemorySlidingWindowStore()
    card_token = "tok_v3_test_card_velocity_01"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Transaction 45 minutes ago (in 1h, 24h, 7d, 30d)
    tx1 = make_test_tx("tx_01", card_token, 20.0, now - timedelta(minutes=45))
    store.record_transaction(tx1)

    # 2. Transaction 2 hours ago (in 24h, 7d, 30d; NOT in 1h)
    tx2 = make_test_tx("tx_02", card_token, 50.0, now - timedelta(hours=2))
    store.record_transaction(tx2)

    # 3. Transaction 3 days ago (in 7d, 30d; NOT in 1h, 24h)
    tx3 = make_test_tx("tx_03", card_token, 100.0, now - timedelta(days=3))
    store.record_transaction(tx3)

    # 4. Transaction 15 days ago (in 30d; NOT in 1h, 24h, 7d)
    tx4 = make_test_tx("tx_04", card_token, 200.0, now - timedelta(days=15))
    store.record_transaction(tx4)

    # 5. Transaction 35 days ago (expired; outside all windows)
    tx5 = make_test_tx("tx_05", card_token, 500.0, now - timedelta(days=35))
    store.record_transaction(tx5)

    stats = store.get_card_velocity_stats(card_token=card_token, reference_time=now, current_amount=40.0)

    # Counts
    assert stats.tx_count_1h == 1
    assert stats.tx_count_24h == 2
    assert stats.tx_count_7d == 3
    assert stats.tx_count_30d == 4

    # Rolling Spend Sums
    assert stats.amount_sum_1h == 20.0
    assert stats.amount_sum_24h == 70.0    # 20 + 50
    assert stats.amount_sum_7d == 170.0   # 20 + 50 + 100

    # 30-day baseline stats (20 + 50 + 100 + 200 = 370 / 4 = 92.5)
    assert stats.amount_mean_30d == 92.5
    assert stats.amount_std_30d > 0.0

    # Ratio to 30d mean: 40.0 / 92.5 ≈ 0.432
    assert stats.amount_ratio_30d == round(40.0 / 92.5, 3)

    # Z-score should be negative since 40.0 < 92.5
    assert stats.amount_zscore_30d < 0.0


def test_merchant_velocity_and_distinct_cards():
    """
    Asserts merchant transaction volume and unique card token count within sliding windows.
    """
    store = InMemorySlidingWindowStore()
    merch_id = "merch_electronics_flagship"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 3 transactions from card A within 1 hour
    tx1 = make_test_tx("tx_m1", "tok_v3_card_alpha_01", 100.0, now - timedelta(minutes=10), merchant_id=merch_id)
    tx2 = make_test_tx("tx_m2", "tok_v3_card_alpha_01", 150.0, now - timedelta(minutes=20), merchant_id=merch_id)
    tx3 = make_test_tx("tx_m3", "tok_v3_card_alpha_01", 200.0, now - timedelta(minutes=30), merchant_id=merch_id)

    # 1 transaction from card B within 1 hour
    tx4 = make_test_tx("tx_m4", "tok_v3_card_bravo_02", 300.0, now - timedelta(minutes=40), merchant_id=merch_id)

    # 1 transaction from card C 5 hours ago (in 24h, not 1h)
    tx5 = make_test_tx("tx_m5", "tok_v3_card_charlie_03", 50.0, now - timedelta(hours=5), merchant_id=merch_id)

    for tx in [tx1, tx2, tx3, tx4, tx5]:
        store.record_transaction(tx)

    m_stats = store.get_merchant_velocity_stats(merchant_id=merch_id, reference_time=now)

    assert m_stats.tx_count_1h == 4
    assert m_stats.tx_count_24h == 5
    assert m_stats.distinct_cards_1h == 2  # card_A and card_B


def test_first_transaction_on_card_neutral_stats():
    """
    Asserts that a brand new card produces clean neutral default statistics without errors.
    """
    store = InMemorySlidingWindowStore()
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    stats = store.get_card_velocity_stats("tok_v3_unseen_card", reference_time=now, current_amount=75.0)

    assert stats.tx_count_1h == 0
    assert stats.tx_count_24h == 0
    assert stats.tx_count_7d == 0
    assert stats.tx_count_30d == 0
    assert stats.amount_sum_1h == 0.0
    assert stats.amount_sum_24h == 0.0
    assert stats.amount_mean_30d == 0.0
    assert stats.amount_std_30d == 0.0
    assert stats.amount_ratio_30d == 1.0
    assert stats.amount_zscore_30d == 0.0


def test_prune_expired_removes_old_events():
    """
    Asserts that prune_expired evicts transactions older than 30 days.
    """
    store = InMemorySlidingWindowStore()
    card_token = "tok_v3_prune_card"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Fresh event: 5 days ago
    tx_fresh = make_test_tx("tx_fresh", card_token, 50.0, now - timedelta(days=5))
    # Stale event: 40 days ago
    tx_stale = make_test_tx("tx_stale", card_token, 100.0, now - timedelta(days=40))

    store.record_transaction(tx_fresh)
    store.record_transaction(tx_stale)

    pruned = store.prune_expired(reference_time=now, max_window_seconds=30 * 86400)
    assert pruned >= 1

    stats = store.get_card_velocity_stats(card_token, reference_time=now, current_amount=50.0)
    assert stats.tx_count_30d == 1
    assert stats.amount_sum_7d == 50.0
