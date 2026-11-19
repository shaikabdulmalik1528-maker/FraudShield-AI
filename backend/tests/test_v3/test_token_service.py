"""
Unit tests for FraudShield 3.0 Card Tokenization & Sanitization Service.
Verifies PCI-DSS compliance, Luhn algorithm, determinism, and zero-raw-PAN assertions.
"""

import pytest
from backend.app.v3.services.token_service import KmsTokenService
from backend.app.v3.schemas.canonical import CardNetwork


# Known test card numbers adhering to Luhn check
VALID_VISA = "4532015112830366"
VALID_MASTERCARD = "5424180123456789"
VALID_AMEX = "378282246310005"
VALID_DISCOVER = "6011111111111117"
INVALID_LUHN = "4532015112830367"  # Checksum altered by 1


def test_luhn_algorithm_validation():
    """Verifies Luhn validation detects valid and corrupted card numbers."""
    assert KmsTokenService.validate_luhn(VALID_VISA) is True
    assert KmsTokenService.validate_luhn(VALID_MASTERCARD) is True
    assert KmsTokenService.validate_luhn(VALID_AMEX) is True
    assert KmsTokenService.validate_luhn(VALID_DISCOVER) is True
    assert KmsTokenService.validate_luhn(INVALID_LUHN) is False
    assert KmsTokenService.validate_luhn("12345") is False  # Too short


def test_tokenization_determinism():
    """Asserts that identical PANs under the same salt yield identical tokens."""
    service = KmsTokenService(salt_key="test-salt-alpha")
    token_1 = service.tokenize_pan(VALID_VISA)
    token_2 = service.tokenize_pan(VALID_VISA)

    assert token_1 == token_2
    assert token_1.startswith("tok_v3_")
    assert len(token_1) == 7 + 32  # Prefix + 32 hex chars


def test_tokenization_salting_uniqueness():
    """Asserts that identical PANs under different salts produce different tokens."""
    service_a = KmsTokenService(salt_key="salt-alpha")
    service_b = KmsTokenService(salt_key="salt-beta")

    token_a = service_a.tokenize_pan(VALID_VISA)
    token_b = service_b.tokenize_pan(VALID_VISA)

    assert token_a != token_b


def test_zero_raw_pan_leakage():
    """Security audit: verifies cleartext PAN never appears anywhere in the token."""
    service = KmsTokenService()
    token = service.tokenize_pan(VALID_VISA)

    assert VALID_VISA not in token
    assert VALID_VISA[4:12] not in token  # Middle 8 digits cannot appear


def test_bin_and_last4_extraction():
    """Verifies accurate extraction of Bank Identification Number and last 4 digits."""
    card_bin, last4 = KmsTokenService.extract_bin_and_last4(VALID_VISA)
    assert card_bin == "453201"
    assert last4 == "0366"

    with pytest.raises(ValueError):
        KmsTokenService.extract_bin_and_last4("1234567")  # Too short for BIN + last4


def test_card_network_detection():
    """Verifies correct IIN/BIN prefix network classification."""
    assert KmsTokenService.detect_network(VALID_VISA) == CardNetwork.VISA
    assert KmsTokenService.detect_network(VALID_MASTERCARD) == CardNetwork.MASTERCARD
    assert KmsTokenService.detect_network(VALID_AMEX) == CardNetwork.AMEX
    assert KmsTokenService.detect_network(VALID_DISCOVER) == CardNetwork.DISCOVER
    assert KmsTokenService.detect_network("9999999999999999") == CardNetwork.OTHER


def test_mask_pan_format():
    """Verifies PCI-DSS masked PAN formatting."""
    masked = KmsTokenService.mask_pan(VALID_VISA)
    assert masked.startswith("453201")
    assert masked.endswith("0366")
    assert "XXXXXX" in masked
    assert len(masked) == len(VALID_VISA)
