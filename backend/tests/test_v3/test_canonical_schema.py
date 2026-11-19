"""
Unit tests for FraudShield 3.0 Canonical Transaction Schema.
Verifies Pydantic v2 validation contracts, immutability, and boundary rules.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)


def sample_valid_canonical():
    return CanonicalTransaction(
        transaction_id="tx_test_1001",
        timestamp=datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc),
        amount=125.50,
        currency="USD",
        card_pan_token="tok_v3_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        card_bin="453201",
        card_last4="0366",
        card_network=CardNetwork.VISA,
        card_type=CardType.DEBIT,
        merchant_id="merch_acme_corp_88",
        mcc="5411",  # Grocery Stores
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP,
        pos_entry_mode="05",
        metadata={"terminal_type": "ATTENDED"}
    )


def test_valid_canonical_transaction_construction():
    """Asserts that a valid canonical transaction instantiates correctly."""
    tx = sample_valid_canonical()
    assert tx.transaction_id == "tx_test_1001"
    assert tx.amount == 125.50
    assert tx.currency == "USD"
    assert tx.mcc == "5411"
    assert tx.card_network == CardNetwork.VISA
    assert tx.channel == PaymentChannel.POS_CHIP


def test_negative_amount_rejection():
    """Asserts that negative amounts fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        CanonicalTransaction(
            transaction_id="tx_neg",
            timestamp=datetime.now(timezone.utc),
            amount=-10.00,  # Invalid
            currency="USD",
            card_pan_token="tok_v3_test12345678901234567890",
            card_bin="453201",
            card_last4="0366",
            merchant_id="merch_1",
            mcc="5411"
        )
    assert "Input should be greater than or equal to 0" in str(exc_info.value)


def test_invalid_mcc_rejection():
    """Asserts that non-4-digit or non-numeric MCC codes are rejected."""
    # Letters in MCC
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            transaction_id="tx_bad_mcc",
            timestamp=datetime.now(timezone.utc),
            amount=50.00,
            currency="USD",
            card_pan_token="tok_v3_test12345678901234567890",
            card_bin="453201",
            card_last4="0366",
            merchant_id="merch_1",
            mcc="ABCD"  # Invalid
        )

    # 3 digits in MCC
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            transaction_id="tx_short_mcc",
            timestamp=datetime.now(timezone.utc),
            amount=50.00,
            currency="USD",
            card_pan_token="tok_v3_test12345678901234567890",
            card_bin="453201",
            card_last4="0366",
            merchant_id="merch_1",
            mcc="541"  # Invalid length
        )


def test_invalid_currency_code_rejection():
    """Asserts that non-3-letter currency codes are rejected."""
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            transaction_id="tx_bad_curr",
            timestamp=datetime.now(timezone.utc),
            amount=50.00,
            currency="US",  # Too short
            card_pan_token="tok_v3_test12345678901234567890",
            card_bin="453201",
            card_last4="0366",
            merchant_id="merch_1",
            mcc="5411"
        )


def test_canonical_immutability():
    """Asserts that CanonicalTransaction is frozen and cannot be mutated."""
    tx = sample_valid_canonical()
    with pytest.raises(ValidationError):
        tx.amount = 999.00  # Mutation forbidden on frozen model


def test_extra_fields_forbidden():
    """Asserts that arbitrary unauthorized fields cannot be injected."""
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            transaction_id="tx_extra",
            timestamp=datetime.now(timezone.utc),
            amount=50.00,
            currency="USD",
            card_pan_token="tok_v3_test12345678901234567890",
            card_bin="453201",
            card_last4="0366",
            merchant_id="merch_1",
            mcc="5411",
            unauthorized_field="malicious_payload"  # Extra forbidden
        )
