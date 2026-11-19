"""
Unit tests for FraudShield 3.0 IEEE-CIS Tabular Dataset Adapter.
Verifies parsing, timestamp synthesis, Vesta card tokenization, and domain integrity assertions.
"""

import pytest
from datetime import datetime, timezone
from backend.app.v3.adapters.ieee_cis_adapter import IeeeCisAdapter, IEEE_CIS_REFERENCE_EPOCH
from backend.app.v3.schemas.canonical import CardNetwork, CardType, PaymentChannel


def sample_ieee_cis_dict():
    return {
        "TransactionID": 2987004,
        "TransactionDT": 86400,        # Exactly 1 day (86400s) after reference epoch
        "TransactionAmt": 50.00,
        "ProductCD": "W",
        "card1": 13926,                # Issuer bank code
        "card2": 150.0,
        "card3": 150.0,
        "card4": "visa",
        "card5": 142.0,
        "card6": "credit",
        "addr1": 315.0,
        "addr2": 87.0,
        "dist1": 19.0,
        "P_emaildomain": "gmail.com",
        "R_emaildomain": "anonymous.info",
        "C1": 1.0,
        "C2": 1.0,
        "D1": 14.0,
        "V1": 1.0,
        "V2": 1.0,
        "DeviceType": "desktop",
        "DeviceInfo": "MacOS"
    }


def test_ieee_cis_valid_adaptation():
    """Asserts that a valid IEEE-CIS tabular record normalizes into CanonicalTransaction."""
    adapter = IeeeCisAdapter()
    raw = sample_ieee_cis_dict()

    is_valid, errors = adapter.validate(raw)
    assert is_valid is True
    assert len(errors) == 0

    tx = adapter.adapt(raw)
    assert tx.transaction_id == "ieee_2987004"
    assert tx.amount == 50.00
    assert tx.currency == "USD"
    assert tx.card_network == CardNetwork.VISA
    assert tx.card_type == CardType.CREDIT
    assert tx.channel == PaymentChannel.ECOMMERCE
    assert tx.mcc == "5311"  # ProductCD 'W' maps to 5311

    # Timestamp verification: exactly 1 day after Dec 1, 2017
    assert tx.timestamp.year == 2017
    assert tx.timestamp.month == 12
    assert tx.timestamp.day == 2
    assert tx.timestamp.hour == 0
    assert tx.timestamp.minute == 0


def test_ieee_cis_domain_distinction_assertion():
    """Asserts that IEEE-CIS data is explicitly flagged as NOT native ISO 8583 data."""
    adapter = IeeeCisAdapter()
    raw = sample_ieee_cis_dict()
    tx = adapter.adapt(raw)

    assert tx.metadata["is_native_iso8583"] is False
    assert tx.metadata["source_protocol"] == "IEEE_CIS_VESTA_TABULAR"
    assert "vesta_features" in tx.metadata
    assert tx.metadata["vesta_features"]["C1"] == 1.0
    assert tx.metadata["vesta_features"]["V1"] == 1.0


def test_ieee_cis_card_tokenization():
    """Asserts that card token is deterministically generated from card features."""
    adapter = IeeeCisAdapter()
    raw_1 = sample_ieee_cis_dict()
    raw_2 = sample_ieee_cis_dict()

    tx_1 = adapter.adapt(raw_1)
    tx_2 = adapter.adapt(raw_2)

    assert tx_1.card_pan_token == tx_2.card_pan_token
    assert tx_1.card_pan_token.startswith("tok_v3_")


def test_ieee_cis_missing_mandatory_columns():
    """Asserts that records missing required columns are rejected."""
    adapter = IeeeCisAdapter()
    raw = sample_ieee_cis_dict()
    del raw["TransactionAmt"]
    del raw["TransactionDT"]

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("Missing mandatory 'TransactionAmt'" in err for err in errors)
    assert any("Missing mandatory 'TransactionDT'" in err for err in errors)

    with pytest.raises(ValueError):
        adapter.adapt(raw)


def test_ieee_cis_negative_amount_rejection():
    """Asserts that zero or negative transaction amounts are rejected."""
    adapter = IeeeCisAdapter()
    raw = sample_ieee_cis_dict()
    raw["TransactionAmt"] = -5.0

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("'TransactionAmt' must be greater than zero" in err for err in errors)
