"""
Unit tests for FraudShield 3.0 ISO 8583 Message Ingestion Adapter.
Tests parsing, validation, amount conversion, MTI classification, and raw frame decoding.
"""

import pytest
from datetime import datetime, timezone
from backend.app.v3.adapters.iso8583_adapter import Iso8583Adapter
from backend.app.v3.schemas.canonical import PaymentChannel, CardNetwork


VALID_VISA_PAN = "4532015112830366"  # Valid Luhn


def sample_iso8583_dict_payload():
    return {
        "mti": "0100",
        "de2": VALID_VISA_PAN,
        "de3": "000000",          # Goods and Services Purchase
        "de4": 12550,             # 125.50 in cents (minor currency units)
        "de7": "1117143000",       # Nov 17, 14:30:00
        "de11": "048291",         # STAN
        "de14": "2811",           # Expiration YYMM
        "de18": "5411",           # Grocery Stores
        "de19": "840",            # USA
        "de22": "051",            # POS Chip Entry
        "de25": "00",             # Normal Presentment
        "de37": "000000048291",   # RRN
        "de41": "TERM0042",       # Terminal ID
        "de42": "MERCH8829104812",# Merchant ID
        "de43": "SUPERMARKET ACME BRUSSELS BE",
        "de49": "840"             # USD
    }


def test_iso8583_valid_auth_request_adaptation():
    """Asserts that a valid MTI 0100 message is correctly normalized to CanonicalTransaction."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()

    is_valid, errors = adapter.validate(raw)
    assert is_valid is True
    assert len(errors) == 0

    tx = adapter.adapt(raw)
    assert tx.amount == 125.50
    assert tx.currency == "USD"
    assert tx.mcc == "5411"
    assert tx.card_bin == "453201"
    assert tx.card_last4 == "0366"
    assert tx.card_network == CardNetwork.VISA
    assert tx.channel == PaymentChannel.POS_CHIP
    assert tx.merchant_id == "MERCH8829104812"
    assert tx.timestamp.month == 11
    assert tx.timestamp.day == 17
    assert tx.timestamp.hour == 14
    assert tx.timestamp.minute == 30

    # Assert zero cleartext PAN in canonical transaction
    assert VALID_VISA_PAN not in tx.card_pan_token
    assert tx.card_pan_token.startswith("tok_v3_")


def test_iso8583_amount_minor_units_conversion():
    """Verifies that integer cents are converted accurately to decimal currency units."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()

    # 1 cent
    raw["de4"] = 1
    tx = adapter.adapt(raw)
    assert tx.amount == 0.01

    # 1,000,000 cents ($10,000.00)
    raw["de4"] = 1000000
    tx = adapter.adapt(raw)
    assert tx.amount == 10000.00


def test_iso8583_invalid_mti_rejection():
    """Asserts that invalid or unsupported MTIs are rejected."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()
    raw["mti"] = "9999"  # Unsupported

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("Invalid or missing MTI" in err for err in errors)

    with pytest.raises(ValueError):
        adapter.adapt(raw)


def test_iso8583_luhn_failure_rejection():
    """Asserts that corrupted PANs fail Luhn validation during ISO 8583 ingestion."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()
    raw["de2"] = "4532015112830367"  # Corrupted checksum

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("Luhn checksum validation" in err for err in errors)


def test_iso8583_missing_mandatory_fields_rejection():
    """Asserts that missing mandatory data elements fail validation."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()
    del raw["de4"]   # Remove Amount
    del raw["de18"]  # Remove MCC

    is_valid, errors = adapter.validate(raw)
    assert is_valid is False
    assert any("Missing mandatory DE 4" in err for err in errors)
    assert any("Missing mandatory DE 18" in err for err in errors)


def test_iso8583_financial_presentment_mti_0200():
    """Verifies adaptation of MTI 0200 (Financial Transaction)."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()
    raw["mti"] = "0200"

    tx = adapter.adapt(raw)
    assert tx.metadata["mti"] == "0200"
    assert tx.metadata["source_protocol"] == "ISO_8583"


def test_iso8583_reversal_advice_mti_0420():
    """Verifies adaptation of MTI 0420 (Reversal Advice)."""
    adapter = Iso8583Adapter()
    raw = sample_iso8583_dict_payload()
    raw["mti"] = "0420"
    raw["de4"] = 0  # Reversals can carry 0 or full amount

    is_valid, errors = adapter.validate(raw)
    assert is_valid is True
    tx = adapter.adapt(raw)
    assert tx.metadata["mti"] == "0420"


def test_iso8583_raw_message_frame_parsing():
    """Verifies parsing of raw ASCII/hex bitmap message frames."""
    adapter = Iso8583Adapter()
    # MTI(0100) + 16-hex bitmap + piped data fields
    raw_frame = f"01007020000000000000{VALID_VISA_PAN}|000000|12550|1117143000|048291|5411|TERM0042|MERCH8829104812|840"
    
    parsed = adapter.parse_raw_message_frame(raw_frame)
    assert parsed["mti"] == "0100"
    assert parsed["de2"] == VALID_VISA_PAN
    assert parsed["de4"] == "12550"
    assert parsed["de18"] == "5411"

    # Adapter adapt on parsed dict
    tx = adapter.adapt(parsed)
    assert tx.amount == 125.50
    assert tx.mcc == "5411"
