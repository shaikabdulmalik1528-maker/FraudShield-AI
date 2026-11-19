"""
Unit tests for Architecture Review Refinements (SEC-01, SEC-02, DATA-01).
Verifies KMS salt security enforcement, Pydantic model serialization PAN masking, and IEEE-CIS account disambiguation.
"""

import json
import pytest
from backend.app.v3.services.token_service import KmsTokenService
from backend.app.v3.schemas.iso8583 import Iso8583ParsedPayload, Iso8583Mti
from backend.app.v3.adapters.ieee_cis_adapter import IeeeCisAdapter


def test_sec_01_kms_salt_enforcement(monkeypatch):
    """Asserts that production mode or enforce_configured_salt rejects insecure default fallback."""
    # Ensure environment secret is unset for this specific test
    monkeypatch.delenv("FRAUDSHIELD_TOKEN_SALT", raising=False)

    # When explicitly enforcing configured salt with no provider/salt, it must raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        KmsTokenService(salt_key=None, enforce_configured_salt=True)
    assert "Production configuration failure" in str(exc_info.value)

    # When providing a custom key provider callable, it should initialize securely
    def mock_kms_provider():
        return "aws-kms-managed-salt-production-9988"

    service = KmsTokenService(key_provider=mock_kms_provider, enforce_configured_salt=True)
    assert service.is_custom_salt is True
    tok = service.tokenize_pan("4532015112830366")
    assert tok.startswith("tok_v3_")


def test_sec_02_iso8583_pan_field_serialization_masking():
    """
    Asserts that Iso8583ParsedPayload masks raw PAN upon serialization (model_dump / JSON).
    Guarantees zero plain PAN leakage in logs or API payloads.
    """
    raw_pan = "4532015112830366"
    payload = Iso8583ParsedPayload(
        mti=Iso8583Mti.AUTH_REQUEST,
        pan=raw_pan,
        amount_cents=1000,
        transmission_datetime="0615120000",
        stan="123456",
        mcc="5411",
        terminal_id="TERM01",
        merchant_id="MERCH01"
    )

    # In-memory Python attribute is accessible to adapter
    assert payload.pan == raw_pan

    # Serialized dictionary must mask PAN
    dumped_dict = payload.model_dump()
    assert dumped_dict["pan"] != raw_pan
    assert "XXXXXX" in dumped_dict["pan"]
    assert dumped_dict["pan"].startswith("453201")
    assert dumped_dict["pan"].endswith("0366")

    # Serialized JSON must mask PAN
    dumped_json = payload.model_dump_json()
    assert raw_pan not in dumped_json
    assert "453201XXXXXX0366" in dumped_json


def test_data_01_ieee_cis_addr1_account_disambiguation():
    """
    Asserts that IEEE-CIS records with identical card1-3 but different addr1
    produce distinct card tokens, preventing cross-cardholder collision.
    """
    token_service = KmsTokenService(salt_key="test-ieee-disambiguation-salt")
    adapter = IeeeCisAdapter(token_service=token_service)

    base_record = {
        "TransactionID": 10001,
        "TransactionDT": 100,
        "TransactionAmt": 50.0,
        "ProductCD": "W",
        "card1": 13926,
        "card2": 150.0,
        "card3": 150.0,
        "card4": "visa",
        "card6": "credit"
    }

    # Cardholder A at billing address 315
    record_a = dict(base_record, TransactionID=10001, addr1=315.0)
    # Cardholder B at billing address 476
    record_b = dict(base_record, TransactionID=10002, addr1=476.0)

    tx_a = adapter.adapt(record_a)
    tx_b = adapter.adapt(record_b)

    assert tx_a.card_pan_token != tx_b.card_pan_token
    assert tx_a.card_pan_token.startswith("tok_v3_")
    assert tx_b.card_pan_token.startswith("tok_v3_")
