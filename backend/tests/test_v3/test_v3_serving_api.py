"""
Integration tests for FraudShield 3.0 Real-Time Serving API (`/api/v3/predict`).
Verifies ISO 8583, IEEE-CIS, and Generic JSON endpoints, request size limits,
PCI-DSS zero PAN exposure, batch prediction, and operational telemetry.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

VALID_PAN = "4532015112830366"
SERVICE_HEADERS = {"X-API-Key": "fs3_service_gw_key_2026_dev"}
ADMIN_HEADERS = {"X-API-Key": "fs3_admin_sec_key_2026_dev"}
ANALYST_HEADERS = {"X-API-Key": "fs3_analyst_ui_key_2026_dev"}


def test_v3_predict_iso8583_payload():
    """Verifies that an ISO 8583 dictionary payload is adapted and scored successfully."""
    payload = {
        "mti": "0100",
        "pan": VALID_PAN,
        "de4": "15000",        # $150.00 USD
        "de7": "0615120000",
        "de11": "654321",
        "de18": "5411",
        "de41": "TERM_POS_01",
        "de42": "MERCH_RETAIL_01",
        "de49": "840"          # USD
    }

    response = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert "transaction_id" in data
    assert data["amount"] == 150.0
    assert data["currency"] == "USD"
    assert "fraud_probability" in data
    assert "risk_score" in data
    assert data["action"] in ("APPROVE", "STEP_UP_2FA", "MANUAL_REVIEW", "IMMEDIATE_BLOCK")
    assert "model_version" in data
    assert data["features_used"] > 0
    assert data["latency_ms"] > 0

    # PCI-DSS Zero Cleartext PAN Audit
    response_text = response.text
    assert VALID_PAN not in response_text
    assert VALID_PAN[4:12] not in response_text
    assert data["card_masked"].startswith("453201")
    assert data["card_masked"].endswith("0366")


def test_v3_predict_ieee_cis_payload():
    """Verifies that an IEEE-CIS dictionary payload is adapted and scored successfully."""
    payload = {
        "TransactionID": "3999999",
        "TransactionDT": 15000000,
        "TransactionAmt": 85.50,
        "ProductCD": "W",
        "card1": 13500,
        "card2": 240.0,
        "card3": 150.0,
        "card4": "visa",
        "card5": 226.0,
        "card6": "credit",
        "addr1": 299.0,
        "addr2": 87.0
    }

    response = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["transaction_id"] == "ieee_3999999"
    assert data["amount"] == 85.50
    assert "fraud_probability" in data
    assert data["is_duplicate"] is False


def test_v3_predict_generic_json_payload():
    """Verifies that generic raw JSON payload scores successfully."""
    payload = {
        "transaction_id": "tx_gen_api_01",
        "timestamp": "2026-06-15T12:00:00Z",
        "amount": 42.00,
        "currency": "USD",
        "card_number": VALID_PAN,
        "merchant_id": "merch_cafe",
        "mcc": "5812",
        "channel": "POS_CONTACTLESS"
    }

    response = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["transaction_id"] == "tx_gen_api_01"
    assert data["amount"] == 42.00
    assert VALID_PAN not in response.text


def test_v3_predict_invalid_payload_validation_error():
    """Asserts that invalid/malformed payloads return HTTP 422 Unprocessable Entity."""
    # Negative amount
    invalid_payload = {
        "transaction_id": "tx_invalid",
        "amount": -50.0,
        "card_number": VALID_PAN
    }
    response = client.post("/api/v3/predict", json=invalid_payload, headers=SERVICE_HEADERS)
    assert response.status_code == 422


def test_v3_predict_empty_payload_rejection():
    """Asserts that empty payload returns HTTP 400 Bad Request."""
    response = client.post("/api/v3/predict", json={}, headers=SERVICE_HEADERS)
    assert response.status_code == 400


def test_v3_batch_predict_endpoint():
    """Verifies batch scoring of multiple transactions."""
    batch_payload = {
        "transactions": [
            {
                "transaction_id": f"tx_batch_{i}",
                "timestamp": "2026-06-15T12:00:00Z",
                "amount": float(20 + i * 10),
                "currency": "USD",
                "card_number": VALID_PAN,
                "merchant_id": f"merch_batch_{i}",
                "mcc": "5411"
            }
            for i in range(5)
        ]
    }

    response = client.post("/api/v3/batch-predict", json=batch_payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["total_processed"] == 5
    assert len(data["predictions"]) == 5
    assert data["avg_latency_ms"] > 0.0


def test_v3_status_telemetry_endpoint():
    """Verifies the GET /api/v3/status operational telemetry endpoint."""
    response = client.get("/api/v3/status", headers=SERVICE_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "3.0.0"
    assert data["status"] == "OPERATIONAL"
    assert data["model_loaded"] is True
    assert data["optimal_threshold"] == 0.700
    assert "feature_store" in data
    assert "dual_engine_telemetry" in data


def test_v3_reload_endpoint():
    """Verifies the POST /api/v3/reload hot-reload endpoint."""
    response = client.post("/api/v3/reload", headers=ADMIN_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "RELOADED"
    assert data["optimal_threshold"] == 0.700
    assert data["features_loaded"] == 89


def test_v3_unauthenticated_request_rejected():
    """Verifies that missing API key returns HTTP 401 Unauthorized."""
    response = client.post("/api/v3/predict", json={"amount": 10.0})
    assert response.status_code == 401
    assert "Missing authentication credentials" in response.json()["detail"]


def test_v3_unauthorized_role_rejected_for_admin_endpoint():
    """Verifies that SERVICE role cannot trigger admin-only hot-reload."""
    response = client.post("/api/v3/reload", headers=SERVICE_HEADERS)
    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]
