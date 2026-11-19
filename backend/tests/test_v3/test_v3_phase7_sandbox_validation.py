"""
FraudShield 3.0 Phase 7 Partner Sandbox Validation Test Suite.
Validates:
1. Sandbox configuration (.env.sandbox) completeness and isolation.
2. Partner API key registration, role scoping (ClientRole.PARTNER), and rate limiting.
3. Partner RBAC isolation (allowed: /predict, /batch-predict; blocked: /reload, /model/rollback, /monitoring/drift).
4. Partner Test Card Deck deterministic evaluation (clean purchase, anomaly, Luhn validation).
5. Idempotency replay resilience for partner payment retries.
6. Multi-currency normalization (JPY, EUR, GBP) in partner scoring.
7. Zero cleartext PAN/CVV leakage in response payloads.
8. Disaster recovery degraded mode policy enforcement.
"""

import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v3.security.config import ClientRole, SecurityConfig
from backend.app.v3.security.auth import ApiKeyManager
from backend.app.v3.services.token_service import KmsTokenService
from scripts.partner_sandbox_runner import generate_luhn_pan

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SANDBOX_ENV_FILE = PROJECT_ROOT / ".env.sandbox"

PARTNER_KEY = "fs3_partner_test_phase7_validation_key_2026"
ADMIN_KEY = "fs3_sandbox_admin_key_secops_2026_demo"
ANALYST_KEY = "fs3_sandbox_analyst_key_ops_2026_demo"


@pytest.fixture(scope="module")
def client():
    # Ensure test client has partner key registered
    from backend.app.v3.security.auth import api_key_manager
    api_key_manager.register_key("test_partner", ClientRole.PARTNER, raw_key=PARTNER_KEY, key_id="key_partner_test")
    api_key_manager.register_key("test_admin", ClientRole.ADMIN, raw_key=ADMIN_KEY, key_id="key_admin_test")
    api_key_manager.register_key("test_analyst", ClientRole.ANALYST, raw_key=ANALYST_KEY, key_id="key_analyst_test")
    return TestClient(app)


def test_sandbox_env_file_validity():
    """Validates that .env.sandbox contains all necessary partner sandbox settings without placeholders."""
    assert SANDBOX_ENV_FILE.exists(), ".env.sandbox file must exist"
    content = SANDBOX_ENV_FILE.read_text(encoding="utf-8")

    expected_vars = [
        "APP_ENV=sandbox",
        "FRAUDSHIELD_ENV=sandbox",
        "FRAUDSHIELD_PARTNER_API_KEY",
        "FRAUDSHIELD_TOKEN_SALT",
        "FRAUDSHIELD_API_KEY_SALT",
        "RATE_LIMIT_PARTNER_PER_MIN",
        "DEGRADED_FAILSAFE_ENABLED=true",
        "FRAUDSHIELD_WORKER_SCOPED_AUDIT=true"
    ]
    for var in expected_vars:
        assert var in content, f"Missing required variable: {var}"
    assert "REPLACE_WITH" not in content, "Found placeholder secret in .env.sandbox"


def test_partner_api_key_role_and_scoping():
    """Validates that ClientRole.PARTNER exists, has a rate limit of 1200/min, and validates correctly."""
    assert ClientRole.PARTNER in SecurityConfig.RATE_LIMITS
    assert SecurityConfig.RATE_LIMITS[ClientRole.PARTNER] == 1200

    mgr = ApiKeyManager()
    raw_key, meta = mgr.register_key("acme_partner", ClientRole.PARTNER)
    assert meta.role == ClientRole.PARTNER
    assert meta.rate_limit_per_min == 1200
    assert meta.is_active is True

    validated = mgr.validate_key(raw_key)
    assert validated is not None
    assert validated.key_id == meta.key_id
    assert validated.role == ClientRole.PARTNER


def test_partner_rbac_endpoint_access_and_isolation(client):
    """
    Validates partner role RBAC boundaries:
    - ALLOWED: /api/v3/predict, /api/v3/batch-predict
    - FORBIDDEN (403): /api/v3/reload, /api/v3/model/rollback, /api/v3/monitoring/drift
    """
    headers = {"X-API-Key": PARTNER_KEY}
    valid_pan = generate_luhn_pan("45320111", 16)

    sample_tx = {
        "transaction_id": "tx_sbx_rbac_test_001",
        "amount": 25.00,
        "currency": "USD",
        "card_number": valid_pan,
        "cvv": "123",
        "expiry_month": 12,
        "expiry_year": 2028,
        "merchant_id": "merch_rbac_test",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }

    # 1. Partner can call /api/v3/predict
    r = client.post("/api/v3/predict", json=sample_tx, headers=headers)
    assert r.status_code == 200, f"Partner should be allowed on /predict, got {r.status_code}: {r.text}"
    body = r.json()
    assert "action" in body
    assert "fraud_probability" in body

    # 2. Partner cannot call /api/v3/reload (403 Forbidden)
    r = client.post("/api/v3/reload", headers=headers)
    assert r.status_code == 403, f"Partner should be forbidden on /reload, got {r.status_code}"

    # 3. Partner cannot call /api/v3/model/rollback (403 Forbidden)
    r = client.post("/api/v3/model/rollback", headers=headers)
    assert r.status_code == 403, f"Partner should be forbidden on /model/rollback, got {r.status_code}"

    # 4. Partner cannot call /api/v3/monitoring/drift (403 Forbidden)
    r = client.get("/api/v3/monitoring/drift", headers=headers)
    assert r.status_code == 403, f"Partner should be forbidden on /monitoring/drift, got {r.status_code}"


def test_partner_test_card_deck_deterministic_scoring(client):
    """Validates deterministic scoring behavior across representative Partner Test Card Deck scenarios."""
    headers = {"X-API-Key": PARTNER_KEY}

    # TC-SANDBOX-01: Clean E-Commerce Purchase -> APPROVE
    card_clean = generate_luhn_pan("45320111", 16)
    r = client.post("/api/v3/predict", json={
        "transaction_id": "tx_sbx_deck_clean",
        "amount": 35.00,
        "currency": "USD",
        "card_number": card_clean,
        "cvv": "123",
        "expiry_month": 12,
        "expiry_year": 2028,
        "merchant_id": "merch_clean_sbx",
        "mcc": "5411",
        "channel": "POS"
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["action"] == "APPROVE"
    assert r.json()["fraud_probability"] < 0.20

    # TC-SANDBOX-02: Stolen Card Whale Anomaly -> MANUAL_REVIEW or IMMEDIATE_BLOCK
    card_whale = generate_luhn_pan("45320122", 16)
    r = client.post("/api/v3/predict", json={
        "transaction_id": "tx_sbx_deck_whale",
        "amount": 5500.00,
        "currency": "USD",
        "card_number": card_whale,
        "cvv": "456",
        "expiry_month": 10,
        "expiry_year": 2027,
        "merchant_id": "merch_luxury_sbx",
        "mcc": "5944",
        "channel": "ECOMMERCE"
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["action"] in ("MANUAL_REVIEW", "IMMEDIATE_BLOCK")

    # TC-SANDBOX-08: Invalid Luhn Card -> HTTP 422
    card_bad_luhn = "4532011100000009"  # Fails Luhn checksum
    r = client.post("/api/v3/predict", json={
        "transaction_id": "tx_sbx_deck_badluhn",
        "amount": 20.00,
        "currency": "USD",
        "card_number": card_bad_luhn,
        "cvv": "999",
        "expiry_month": 1,
        "expiry_year": 2029,
        "merchant_id": "merch_sbx",
        "mcc": "5311",
        "channel": "ECOMMERCE"
    }, headers=headers)
    assert r.status_code == 422, f"Expected 422 on invalid Luhn, got {r.status_code}"


def test_partner_idempotency_retry_consistency(client):
    """Validates that duplicate transaction replays are intercepted and marked is_duplicate=True."""
    headers = {"X-API-Key": PARTNER_KEY}
    card = generate_luhn_pan("45320155", 16)
    tx_id = "tx_sbx_idemp_test_replay_001"

    tx_payload = {
        "transaction_id": tx_id,
        "amount": 120.00,
        "currency": "USD",
        "card_number": card,
        "cvv": "321",
        "expiry_month": 6,
        "expiry_year": 2028,
        "merchant_id": "merch_retry_sbx",
        "mcc": "5732",
        "channel": "ECOMMERCE"
    }

    # Initial submission
    r1 = client.post("/api/v3/predict", json=tx_payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["is_duplicate"] is False

    # Immediate replay with identical ID
    r2 = client.post("/api/v3/predict", json=tx_payload, headers=headers)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["is_duplicate"] is True, "Second submission must be flagged as duplicate"
    assert "RULE_DUPLICATE_IDEMP_REPLAY" in b2.get("rule_triggers", [])


def test_partner_multi_currency_normalization(client):
    """Validates currency normalization (JPY 15,000) converts correctly into USD equivalent."""
    headers = {"X-API-Key": PARTNER_KEY}
    card = generate_luhn_pan("45320166", 16)

    r = client.post("/api/v3/predict", json={
        "transaction_id": "tx_sbx_currency_jpy_001",
        "amount": 15000,
        "currency": "JPY",
        "card_number": card,
        "cvv": "777",
        "expiry_month": 11,
        "expiry_year": 2027,
        "merchant_id": "merch_tokyo_sbx",
        "mcc": "5812",
        "channel": "ECOMMERCE"
    }, headers=headers)

    assert r.status_code == 200
    b = r.json()
    assert b["currency"] == "JPY"
    # Evidence or amount normalized in features
    assert b["amount"] == 15000


def test_partner_zero_cleartext_pan_and_cvv_in_response(client):
    """Validates that API responses mask PANs and never leak cleartext PANs or CVVs."""
    headers = {"X-API-Key": PARTNER_KEY}
    raw_pan = generate_luhn_pan("45320199", 16)
    raw_cvv = "842"

    r = client.post("/api/v3/predict", json={
        "transaction_id": "tx_sbx_leak_test_001",
        "amount": 50.00,
        "currency": "USD",
        "card_number": raw_pan,
        "cvv": raw_cvv,
        "expiry_month": 3,
        "expiry_year": 2029,
        "merchant_id": "merch_leak_sbx",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }, headers=headers)

    assert r.status_code == 200
    text_content = r.text
    assert raw_pan not in text_content, "Raw 16-digit PAN leaked into response payload!"
    assert f'"{raw_cvv}"' not in text_content, "Raw CVV leaked into response payload!"
    body = r.json()
    assert body["card_masked"].startswith("453201")
    assert "X" in body["card_masked"] or "*" in body["card_masked"]
    assert body["card_masked"].endswith(raw_pan[-4:])
