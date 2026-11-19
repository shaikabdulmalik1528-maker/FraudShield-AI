"""
Unit tests for FraudShield 3.0 Event Idempotency and Out-of-Order Timeline Handling.
Verifies duplicate transaction rejection, replay attack mitigation, and out-of-order arrival sorting.
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


def make_sample_tx(tx_id: str, card_token: str, amount: float, dt: datetime) -> CanonicalTransaction:
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
        merchant_id="merch_acme_corp",
        mcc="5311",
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP
    )


def test_idempotency_duplicate_rejection():
    """
    Asserts that duplicate transaction submissions are rejected and not double-counted.
    """
    store = InMemorySlidingWindowStore()
    card_token = "tok_v3_idemp_card"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    tx = make_sample_tx("tx_unique_001", card_token, 100.0, now - timedelta(minutes=10))

    # First submission succeeds
    first_res = store.record_transaction(tx)
    assert first_res is True
    assert store.is_duplicate_transaction("tx_unique_001") is True

    # Duplicate submission is rejected
    second_res = store.record_transaction(tx)
    assert second_res is False

    # Verify no double-counting in sliding window
    stats = store.get_card_velocity_stats(card_token, reference_time=now, current_amount=50.0)
    assert stats.tx_count_1h == 1
    assert stats.amount_sum_1h == 100.0


def test_out_of_order_event_insertion():
    """
    Asserts that transactions arriving out of chronological order are correctly
    positioned in the sorted timeline without corrupting sliding window statistics.
    """
    store = InMemorySlidingWindowStore()
    card_token = "tok_v3_ordering_card"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Chronological timestamps
    t1 = now - timedelta(minutes=50)  # Earliest
    t2 = now - timedelta(minutes=30)  # Middle
    t3 = now - timedelta(minutes=10)  # Latest

    tx1 = make_sample_tx("tx_t1", card_token, 10.0, t1)
    tx2 = make_sample_tx("tx_t2", card_token, 20.0, t2)
    tx3 = make_sample_tx("tx_t3", card_token, 30.0, t3)

    # Ingest in out-of-order sequence: t3, then t1, then t2
    assert store.record_transaction(tx3) is True
    assert store.record_transaction(tx1) is True
    assert store.record_transaction(tx2) is True

    # Query at reference time 'now' (all 3 in 1h window)
    stats_now = store.get_card_velocity_stats(card_token, reference_time=now, current_amount=40.0)
    assert stats_now.tx_count_1h == 3
    assert stats_now.amount_sum_1h == 60.0  # 10 + 20 + 30

    # Query at intermediate reference time (t2 + 1 second)
    # Strictly prior to (t2 + 1s): only tx1 and tx2 should be included
    stats_inter = store.get_card_velocity_stats(
        card_token,
        reference_time=t2 + timedelta(seconds=1),
        current_amount=25.0
    )
    assert stats_inter.tx_count_1h == 2
    assert stats_inter.amount_sum_1h == 30.0  # 10 + 20


def test_window_boundary_inclusion():
    """
    Asserts that an event at exactly the 1h window boundary (now - 3600s) is correctly included.
    """
    store = InMemorySlidingWindowStore()
    card_token = "tok_v3_boundary_card"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Exactly 3600 seconds ago
    tx_exact = make_sample_tx("tx_edge", card_token, 50.0, now - timedelta(seconds=3600))
    # 3601 seconds ago (just outside 1h)
    tx_outside = make_sample_tx("tx_out", card_token, 50.0, now - timedelta(seconds=3601))

    store.record_transaction(tx_exact)
    store.record_transaction(tx_outside)

    stats = store.get_card_velocity_stats(card_token, reference_time=now, current_amount=50.0)
    assert stats.tx_count_1h == 1
    assert stats.amount_sum_1h == 50.0
    assert stats.tx_count_24h == 2
    assert stats.amount_sum_24h == 100.0
