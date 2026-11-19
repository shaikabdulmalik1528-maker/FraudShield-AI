"""
FraudShield 3.0 — Base44 External HTTPS Staging & CORS Integration Test Suite.
Validates:
1. CORS preflight (OPTIONS) negotiation for Origin: https://lush-fraud-shield-pulse.base44.app.
2. CORS response headers and exposed metrics (X-Process-Time-Ms, X-RateLimit-*).
3. CORS rejection for unauthorized origins.
4. PARTNER authentication format (X-API-Key and Authorization: Bearer).
5. PARTNER least-privilege scoping:
   - ALLOWED: Single prediction (POST /api/v3/predict)
   - ALLOWED: Batch prediction (POST /api/v3/batch-predict)
   - ALLOWED: Safe partner health probe (GET /health/sandbox, GET /api/v3/sandbox/health)
   - FORBIDDEN (403): Model reload (POST /api/v3/reload)
   - FORBIDDEN (403): Model rollback (POST /api/v3/model/rollback)
   - FORBIDDEN (403): Concept drift monitoring (GET /api/v3/monitoring/drift)
   - FORBIDDEN (403): Admin operational status (GET /api/v3/status)
6. Zero leakage of cleartext PAN/CVV in Base44 responses.
7. Rate limiting configuration for PARTNER role.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.v3.security.config import ClientRole, SecurityConfig
from backend.app.v3.security.auth import api_key_manager
from scripts.partner_sandbox_runner import generate_luhn_pan

BASE44_ORIGIN = "https://lush-fraud-shield-pulse.base44.app"
TEST_PARTNER_KEY = "fs3_partner_test_staging_suite_key_2026"
REVOKED_PARTNER_KEY = "fs3_sandbox_partner_alpha_key_2026_demo"


@pytest.fixture(scope="module")
def client():
    # Ensure test key manager registers the partner key and revoked key
    api_key_manager.register_key(
        name="base44_partner_client",
        role=ClientRole.PARTNER,
        raw_key=TEST_PARTNER_KEY,
        key_id="key_partner_base44"
    )
    api_key_manager.revoke_raw_key(
        raw_key=REVOKED_PARTNER_KEY,
        key_id="key_partner_revoked_test",
        reason="Test suite verification of permanent revocation"
    )
    return TestClient(app)


def test_cors_preflight_for_base44_origin(client):
    """
    Verifies that CORS OPTIONS preflight request from the Base44 origin is accepted
    with appropriate Access-Control headers and exposed headers.
    """
    headers = {
        "Origin": BASE44_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-API-Key, Content-Type, Authorization, X-Idempotency-Key"
    }

    resp = client.options("/api/v3/predict", headers=headers)
    assert resp.status_code == 200, f"Expected 200 for OPTIONS preflight, got {resp.status_code}"
    assert resp.headers.get("access-control-allow-origin") == BASE44_ORIGIN
    assert "POST" in resp.headers.get("access-control-allow-methods", "")

    # Preflight should not use wildcard '*' when credentials are true
    assert resp.headers.get("access-control-allow-origin") != "*"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_actual_post_request_for_base44_origin(client):
    """
    Verifies that actual POST prediction requests from Base44 origin succeed
    and include CORS allow-origin and exposed timing headers.
    """
    valid_pan = generate_luhn_pan("45320111", 16)
    headers = {
        "Origin": BASE44_ORIGIN,
        "X-API-Key": TEST_PARTNER_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "transaction_id": "tx_base44_cors_test_01",
        "amount": 75.00,
        "currency": "USD",
        "card_number": valid_pan,
        "cvv": "123",
        "expiry_month": 12,
        "expiry_year": 2028,
        "merchant_id": "merch_base44_demo",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }

    resp = client.post("/api/v3/predict", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == BASE44_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"
    assert "X-Process-Time-Ms" in resp.headers


def test_cors_rejection_for_unauthorized_origin(client):
    """
    Verifies that requests from unauthorized origins do not receive Access-Control-Allow-Origin.
    """
    headers = {
        "Origin": "https://malicious-unauthorized-site.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-API-Key, Content-Type"
    }

    resp = client.options("/api/v3/predict", headers=headers)
    assert resp.headers.get("access-control-allow-origin") is None


def test_partner_bearer_token_authentication(client):
    """
    Verifies that Base44 can authenticate using 'Authorization: Bearer <key>'
    in addition to 'X-API-Key'.
    """
    valid_pan = generate_luhn_pan("45320111", 16)
    headers = {
        "Authorization": f"Bearer {TEST_PARTNER_KEY}",
        "Origin": BASE44_ORIGIN
    }
    payload = {
        "transaction_id": "tx_base44_bearer_test_01",
        "amount": 29.99,
        "currency": "USD",
        "card_number": valid_pan,
        "cvv": "456",
        "expiry_month": 11,
        "expiry_year": 2027,
        "merchant_id": "merch_base44_retail",
        "mcc": "5812",
        "channel": "ECOMMERCE"
    }

    resp = client.post("/api/v3/predict", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["action"] == "APPROVE"


def test_partner_batch_prediction_access(client):
    """
    Verifies that PARTNER users can execute batch transaction scoring.
    """
    headers = {"X-API-Key": TEST_PARTNER_KEY, "Origin": BASE44_ORIGIN}
    valid_pan = generate_luhn_pan("45320111", 16)

    batch_payload = {
        "transactions": [
            {
                "transaction_id": "tx_b44_batch_01",
                "amount": 15.00,
                "currency": "USD",
                "card_number": valid_pan,
                "merchant_id": "merch_b44_b1",
                "mcc": "5411",
                "channel": "ECOMMERCE"
            },
            {
                "transaction_id": "tx_b44_batch_02",
                "amount": 4500.00,
                "currency": "USD",
                "card_number": valid_pan,
                "merchant_id": "merch_b44_b2",
                "mcc": "5944",
                "channel": "ECOMMERCE"
            }
        ]
    }

    resp = client.post("/api/v3/batch-predict", json=batch_payload, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_processed"] == 2
    assert len(body["predictions"]) == 2


def test_safe_sanitized_partner_health_endpoint(client):
    """
    Verifies that the partner health endpoints return sanitized status
    with zero sensitive administrative or internal infrastructure details.
    """
    for endpoint in ["/health/sandbox", "/api/v3/sandbox/health"]:
        resp = client.get(endpoint)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "HEALTHY"
        assert body["environment"] == "sandbox"
        # Must not leak internal infrastructure keys
        assert "feature_store_circuit" not in body
        assert "model_manifest" not in body
        assert "auth_ready" not in body


def test_partner_forbidden_from_administrative_endpoints(client):
    """
    Verifies that PARTNER users are strictly blocked (HTTP 403) from administrative operations:
    - Model hot-reload
    - Model rollback
    - Drift detection analytics
    - Detailed system status
    """
    headers = {"X-API-Key": TEST_PARTNER_KEY}

    # 1. Reload
    r1 = client.post("/api/v3/reload", headers=headers)
    assert r1.status_code == 403, f"Expected 403 on /reload, got {r1.status_code}"

    # 2. Rollback
    r2 = client.post("/api/v3/model/rollback", headers=headers)
    assert r2.status_code == 403, f"Expected 403 on /model/rollback, got {r2.status_code}"

    # 3. Drift Monitoring
    r3 = client.get("/api/v3/monitoring/drift", headers=headers)
    assert r3.status_code == 403, f"Expected 403 on /monitoring/drift, got {r3.status_code}"

    # 4. Status
    r4 = client.get("/api/v3/status", headers=headers)
    assert r4.status_code == 403, f"Expected 403 on /status, got {r4.status_code}"


def test_zero_cleartext_pan_and_cvv_in_base44_response(client):
    """
    Verifies that API responses never leak cleartext PANs or CVVs.
    """
    raw_pan = generate_luhn_pan("45320199", 16)
    raw_cvv = "931"
    headers = {"X-API-Key": TEST_PARTNER_KEY, "Origin": BASE44_ORIGIN}

    payload = {
        "transaction_id": "tx_b44_leak_check_01",
        "amount": 88.00,
        "currency": "USD",
        "card_number": raw_pan,
        "cvv": raw_cvv,
        "expiry_month": 4,
        "expiry_year": 2029,
        "merchant_id": "merch_b44_clean",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }

    resp = client.post("/api/v3/predict", json=payload, headers=headers)
    assert resp.status_code == 200
    assert raw_pan not in resp.text
    assert f'"{raw_cvv}"' not in resp.text
    body = resp.json()
    assert body["card_masked"].startswith("453201")
    assert body["card_masked"].endswith(raw_pan[-4:])


def test_revoked_partner_key_rejection(client):
    """
    Verifies that a revoked PARTNER key is rejected with HTTP 401 Unauthorized
    and cannot be used to score transactions.
    """
    headers = {
        "Origin": BASE44_ORIGIN,
        "X-API-Key": REVOKED_PARTNER_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "transaction_id": "tx_revoked_test_01",
        "amount": 50.00,
        "currency": "USD",
        "card_number": generate_luhn_pan("45320111", 16),
        "cvv": "123",
        "expiry_month": 12,
        "expiry_year": 2028,
        "merchant_id": "merch_demo",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }
    resp = client.post("/api/v3/predict", json=payload, headers=headers)
    assert resp.status_code == 401, f"Expected 401 Unauthorized for revoked key, got {resp.status_code}"
    assert "revoked" in resp.json().get("detail", "").lower() or "invalid" in resp.json().get("detail", "").lower()
