"""
Unit tests for ISO 8583 Currency Exponent Normalization (DOM-02).
Verifies that 0-decimal (JPY), 2-decimal (USD, EUR), and 3-decimal (KWD) currencies
correctly convert minor unit amounts into major unit canonical representations.
"""

import pytest
from backend.app.v3.adapters.iso8583_adapter import Iso8583Adapter
from backend.app.v3.services.token_service import KmsTokenService


@pytest.fixture
def adapter():
    token_service = KmsTokenService(salt_key="test-currency-exponent-salt-1234")
    return Iso8583Adapter(token_service=token_service)


def test_jpy_zero_decimal_currency_conversion(adapter):
    """
    JPY (numeric 392) has 0 minor units.
    DE 4 amount of 5000 must convert to 5000.0 JPY (not 50.00).
    """
    payload = {
        "mti": "0100",
        "pan": "4532015112830366",
        "de4": "5000",
        "de7": "0615120000",
        "de11": "123456",
        "de18": "5411",
        "de41": "TERM0001",
        "de42": "MERCH_TOKYO_01",
        "de49": "392"  # JPY
    }

    tx = adapter.adapt(payload)
    assert tx.currency == "JPY"
    assert tx.amount == 5000.0


def test_usd_two_decimal_currency_conversion(adapter):
    """
    USD (numeric 840) has 2 minor units (cents).
    DE 4 amount of 5000 must convert to 50.00 USD.
    """
    payload = {
        "mti": "0100",
        "pan": "4532015112830366",
        "de4": "5000",
        "de7": "0615120000",
        "de11": "123456",
        "de18": "5411",
        "de41": "TERM0001",
        "de42": "MERCH_NYC_01",
        "de49": "840"  # USD
    }

    tx = adapter.adapt(payload)
    assert tx.currency == "USD"
    assert tx.amount == 50.00


def test_kwd_three_decimal_currency_conversion(adapter):
    """
    KWD (numeric 414) has 3 minor units (fils).
    DE 4 amount of 5000 must convert to 5.000 KWD.
    """
    payload = {
        "mti": "0100",
        "pan": "4532015112830366",
        "de4": "5000",
        "de7": "0615120000",
        "de11": "123456",
        "de18": "5411",
        "de41": "TERM0001",
        "de42": "MERCH_KUWAIT_01",
        "de49": "414"  # KWD
    }

    tx = adapter.adapt(payload)
    assert tx.currency == "KWD"
    assert tx.amount == 5.0


def test_eur_two_decimal_currency_conversion(adapter):
    """
    EUR (numeric 978) has 2 minor units (cents).
    DE 4 amount of 12345 must convert to 123.45 EUR.
    """
    payload = {
        "mti": "0100",
        "pan": "4532015112830366",
        "de4": "12345",
        "de7": "0615120000",
        "de11": "123456",
        "de18": "5411",
        "de41": "TERM0001",
        "de42": "MERCH_PARIS_01",
        "de49": "978"  # EUR
    }

    tx = adapter.adapt(payload)
    assert tx.currency == "EUR"
    assert tx.amount == 123.45
