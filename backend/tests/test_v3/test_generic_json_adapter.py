"""
Unit tests for FraudShield 3.0 Generic E-Commerce REST JSON Adapter.
Tests validation, PAN tokenization, pre-tokenized card ingestion, and canonical mapping.
"""

import pytest
from datetime import datetime, timezone
from backend.app.v3.adapters.generic_json_adapter import GenericJsonAdapter
from backend.app.v3.schemas.canonical import PaymentChannel, CardNetwork


VALID_VISA_PAN = "4532015112830366"


def sample_rest_json_payload():
    return {
        "transaction_id": "rest_ord_88192",
        "timestamp": "2026-11-17T12:00:00+00:00",
        "amount": 89.99,
        "currency": "USD",
        "card_pan": VALID_VISA_PAN,
        "merchant_id": "merch_online_shop_4",
        "mcc": "5999",
        "merchant_country": "USA",
        "channel": "ECOMMERCE",
        "latitude": 37.7749,
        "longitude": -122.4194
    }


def test_generic_json_valid_adaptation():
    """Asserts that a valid REST JSON payload normalizes into CanonicalTransaction."""
    adapter = GenericJsonAdapter()
    raw = sample_rest_json_payload()

    is_valid, errors = adapter.validate(raw)
    assert is_valid is True
    assert len(errors) == 0

    tx = adapter.adapt(raw)
    assert tx.transaction_id == "rest_ord_88192"
    assert tx.amount == 89.99
    assert tx.mcc == "5999"
    assert tx.card_network == CardNetwork.VISA
    assert tx.channel == PaymentChannel.ECOMMERCE
    assert tx.latitude == 37.7749
    assert tx.longitude == -122.4194
    assert VALID_VISA_PAN not in tx.card_pan_token
    assert tx.card_pan_token.startswith("tok_v3_")


def test_generic_json_pretokenized_card_support():
    """Verifies that pre-tokenized transactions can be ingested directly without raw PAN."""
    adapter = GenericJsonAdapter()
    raw = {
        "transaction_id": "rest_pretoken_1",
        "amount": 25.00,
        "card_pan_token": "tok_v3_already_tokenized_hex123456",
        "card_bin": "453201",
        "card_last4": "0366",
        "card_network": "VISA",
        "merchant_id": "merch_gateway_1",
        "mcc": "5411"
    }

    is_valid, errors = adapter.validate(raw)
    assert is_valid is True
    tx = adapter.adapt(raw)
    assert tx.card_pan_token == "tok_v3_already_tokenized_hex123456"
    assert tx.card_bin == "453201"


def test_generic_json_invalid_luhn_rejection():
    """Asserts that raw PAN failing Luhn validation is rejected."""
    adapter = GenericJsonAdapter()
    raw = sample_rest_json_payload()
    raw["card_pan"] = "4532015112830367"  # Corrupted checksum

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("Luhn checksum validation" in err for err in errors)
