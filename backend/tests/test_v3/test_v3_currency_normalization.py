"""
Unit and integration tests for FraudShield 3.0 Currency Normalization (CURR-01).
Verifies ISO 4217 FX rate conversion, stale rate detection, missing rate fallback,
and cross-currency spend aggregation safety in sliding-window feature stores.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.currency import (
    StaticFxCurrencyConverter,
    DEFAULT_FX_RATES_TO_USD
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore


def make_tx_with_currency(
    tx_id: str,
    card_token: str,
    amount: float,
    currency: str,
    dt: datetime
) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=dt,
        amount=amount,
        currency=currency,
        card_pan_token=card_token,
        card_bin="453201",
        card_last4="0366",
        card_network=CardNetwork.VISA,
        card_type=CardType.CREDIT,
        merchant_id="merch_fx_test",
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP
    )


def test_static_fx_conversion_rates():
    """Verifies that major world currencies convert accurately to base USD."""
    converter = StaticFxCurrencyConverter()

    # 100 USD == 100 USD
    assert converter.convert_to_usd(100.0, "USD") == 100.0
    # 100 EUR == 108.50 USD
    assert converter.convert_to_usd(100.0, "EUR") == 108.50
    # 10,000 JPY == 65.00 USD (at 0.0065)
    assert converter.convert_to_usd(10000.0, "JPY") == 65.00
    # 100 KWD == 325.00 USD (at 3.25)
    assert converter.convert_to_usd(100.0, "KWD") == 325.00
    # Zero amount
    assert converter.convert_to_usd(0.0, "EUR") == 0.0


def test_missing_currency_fallback_neutral():
    """Asserts that unlisted currencies fall back gracefully to 1.0 without crashing."""
    converter = StaticFxCurrencyConverter()
    unknown_curr = "XYZ"

    # Should not raise exception
    rate, is_fallback = converter.get_rate(unknown_curr)
    assert is_fallback is True
    assert rate == 1.0
    assert converter.missing_currency_counts[unknown_curr] == 1

    converted = converter.convert_to_usd(50.0, unknown_curr)
    assert converted == 50.0


def test_stale_rate_detection():
    """Asserts that stale exchange rates are accurately flagged after threshold elapsed."""
    old_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    converter = StaticFxCurrencyConverter(stale_threshold_hours=24.0, reference_time=old_time)

    current_time = old_time + timedelta(hours=25)
    assert converter.is_stale(current_time) is True

    fresh_time = old_time + timedelta(hours=10)
    assert converter.is_stale(fresh_time) is False


def test_cross_currency_sliding_window_normalization():
    """
    CURR-01 Core Validation:
    Asserts that consecutive transactions in JPY and USD do NOT sum directly (which
    would produce 10,100 and cause an artificial 100x baseline spike).
    Instead, spend is normalized into USD (~$165.00).
    """
    converter = StaticFxCurrencyConverter()
    store = InMemorySlidingWindowStore(currency_converter=converter)
    card_token = "tok_v3_multi_currency_card"
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Tx 1: 10,000 JPY 30 minutes ago (≈ $65.00 USD)
    tx_jpy = make_tx_with_currency("tx_jpy_01", card_token, 10000.0, "JPY", now - timedelta(minutes=30))
    # Tx 2: 100 USD 15 minutes ago ($100.00 USD)
    tx_usd = make_tx_with_currency("tx_usd_02", card_token, 100.0, "USD", now - timedelta(minutes=15))

    store.record_transaction(tx_jpy)
    store.record_transaction(tx_usd)

    # Query velocity for current transaction of $50.00 USD
    stats = store.get_card_velocity_stats(card_token, reference_time=now, current_amount=50.0, currency="USD")

    # Counts
    assert stats.tx_count_1h == 2
    # Rolling spend must be $65.00 + $100.00 = $165.00 (NOT 10,100!)
    assert pytest.approx(stats.amount_sum_1h, abs=0.1) == 165.00
    # Mean 30d must be $165 / 2 = $82.50
    assert pytest.approx(stats.amount_mean_30d, abs=0.1) == 82.50
    # Spend ratio for $50 USD against $82.50 USD baseline is 50 / 82.50 ≈ 0.606
    assert stats.amount_ratio_30d < 1.0
