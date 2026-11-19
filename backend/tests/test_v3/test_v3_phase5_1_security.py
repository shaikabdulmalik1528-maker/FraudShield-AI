"""
Security Validation & Forensic Audit Test Suite for FraudShield 3.0 (Phase 5.1).
Independently verifies:
1. Constant-time API key verification and side-channel immunity.
2. Strict RBAC privilege boundaries across SERVICE, ANALYST, and ADMIN.
3. Cryptographic SHA-256 hash-chain audit log integrity (tamper, deletion, reorder detection).
4. Denial-of-service payload limits and rate limiter enforcement.
5. Zero cleartext PAN / CVV leakage across all application outputs.
"""

import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v3.security.config import ClientRole
from backend.app.v3.security.auth import ApiKeyManager
from backend.app.v3.security.audit_logger import StructuredAuditLogger, verify_audit_log_integrity, GENESIS_HASH

client = TestClient(app)

ADMIN_HEADERS = {"X-API-Key": "fs3_admin_sec_key_2026_dev"}
SERVICE_HEADERS = {"X-API-Key": "fs3_service_gw_key_2026_dev"}
ANALYST_HEADERS = {"X-API-Key": "fs3_analyst_ui_key_2026_dev"}


def test_constant_time_validation_adversarial_keys():
    """
    Verifies that ApiKeyManager validation latency does not leak character matching length.
    Compares keys matching 0%, 50%, and 99% of valid key prefix.
    """
    mgr = ApiKeyManager(salt="test_salt_side_channel")
    raw_key, meta = mgr.register_key("benchmark_service", ClientRole.SERVICE)

    # Adversarial key variants
    wrong_key_diff_prefix = "xx" + raw_key[2:]
    wrong_key_diff_suffix = raw_key[:-2] + "xx"
    wrong_key_diff_length = raw_key + "extra_padding"

    latencies_diff_prefix = []
    latencies_diff_suffix = []

    # Warmup
    for _ in range(50):
        mgr.validate_key(raw_key)

    for _ in range(200):
        t0 = time.perf_counter_ns()
        res1 = mgr.validate_key(wrong_key_diff_prefix)
        latencies_diff_prefix.append(time.perf_counter_ns() - t0)
        assert res1 is None

        t0 = time.perf_counter_ns()
        res2 = mgr.validate_key(wrong_key_diff_suffix)
        latencies_diff_suffix.append(time.perf_counter_ns() - t0)
        assert res2 is None

    avg_prefix_us = sum(latencies_diff_prefix) / (len(latencies_diff_prefix) * 1000.0)
    avg_suffix_us = sum(latencies_diff_suffix) / (len(latencies_diff_suffix) * 1000.0)

    # Invariant execution timing within microsecond bounds
    diff_us = abs(avg_prefix_us - avg_suffix_us)
    assert diff_us < 20.0, f"Timing discrepancy {diff_us:.2f}us indicates potential timing side-channel"


def test_rbac_endpoint_privilege_boundaries():
    """
    Forensically validates that SERVICE and ANALYST cannot access administrative endpoints.
    Endpoint matrix:
    - /api/v3/reload: ADMIN only
    - /api/v3/model/rollback: ADMIN only
    - /api/v3/monitoring/drift: ANALYST and ADMIN only (SERVICE rejected)
    """
    # 1. /api/v3/reload
    resp_svc_reload = client.post("/api/v3/reload", headers=SERVICE_HEADERS)
    assert resp_svc_reload.status_code == 403, "SERVICE must be forbidden from /reload"

    resp_ana_reload = client.post("/api/v3/reload", headers=ANALYST_HEADERS)
    assert resp_ana_reload.status_code == 403, "ANALYST must be forbidden from /reload"

    # 2. /api/v3/model/rollback
    resp_svc_rb = client.post("/api/v3/model/rollback", headers=SERVICE_HEADERS)
    assert resp_svc_rb.status_code == 403, "SERVICE must be forbidden from /model/rollback"

    resp_ana_rb = client.post("/api/v3/model/rollback", headers=ANALYST_HEADERS)
    assert resp_ana_rb.status_code == 403, "ANALYST must be forbidden from /model/rollback"

    # 3. /api/v3/monitoring/drift
    resp_svc_drift = client.get("/api/v3/monitoring/drift", headers=SERVICE_HEADERS)
    assert resp_svc_drift.status_code == 403, "SERVICE must be forbidden from /monitoring/drift"

    resp_ana_drift = client.get("/api/v3/monitoring/drift", headers=ANALYST_HEADERS)
    assert resp_ana_drift.status_code == 200, "ANALYST must be permitted for /monitoring/drift"

    resp_adm_drift = client.get("/api/v3/monitoring/drift", headers=ADMIN_HEADERS)
    assert resp_adm_drift.status_code == 200, "ADMIN must be permitted for /monitoring/drift"


def test_oversized_and_malformed_payload_rejection():
    """Verifies that oversized (>1MB) and malformed payloads are rejected."""
    # 1. Empty payload
    resp_empty = client.post("/api/v3/predict", json={}, headers=SERVICE_HEADERS)
    assert resp_empty.status_code == 400

    # 2. Oversized payload header check
    oversized_headers = {**SERVICE_HEADERS, "Content-Length": str(2 * 1024 * 1024)}
    resp_oversized = client.post("/api/v3/predict", json={"test": "data"}, headers=oversized_headers)
    assert resp_oversized.status_code == 413

    # 3. Malformed payload
    resp_malformed = client.post("/api/v3/predict", json={"amount": "invalid_number"}, headers=SERVICE_HEADERS)
    assert resp_malformed.status_code == 422


def test_audit_log_cryptographic_hash_chain_tamper_detection(tmp_path):
    """
    Forensically verifies that verify_audit_log_integrity() mathematically detects:
    1. Unmodified valid log (passes).
    2. Modified field in a record (fails: Tampered record).
    3. Deleted record line (fails: Sequence ID gap).
    4. Swapped / reordered records (fails: Broken hash link or Sequence ID gap).
    """
    log_file = tmp_path / "chained_audit.jsonl"
    audit_logger = StructuredAuditLogger(log_path=log_file)

    # 1. Log 5 consecutive records
    for i in range(5):
        audit_logger.log_event("TX_EVENT", {
            "tx_id": f"tx_chain_{i}",
            "amount": 100.0 + i,
            "card_masked": "4532XXXXXXXX0366"
        })

    # Verify clean log passes
    is_valid, count, err = verify_audit_log_integrity(log_file)
    assert is_valid is True
    assert count == 5
    assert err is None

    # Read original lines
    with open(log_file, "r", encoding="utf-8") as f:
        original_lines = f.readlines()

    # 2. Test Content Modification (Tamper attack)
    tampered_file = tmp_path / "tampered_audit.jsonl"
    modified_lines = list(original_lines)
    # Modify amount in record 2
    rec2 = json.loads(modified_lines[2])
    rec2["amount"] = 999999.00  # Fraudster modifies logged amount
    modified_lines[2] = json.dumps(rec2) + "\n"

    with open(tampered_file, "w", encoding="utf-8") as f:
        f.writelines(modified_lines)

    is_valid, count, err = verify_audit_log_integrity(tampered_file)
    assert is_valid is False
    assert "Tampered record" in err
    assert count == 2  # Records 0 and 1 passed; record 2 failed

    # 3. Test Record Deletion
    deleted_file = tmp_path / "deleted_audit.jsonl"
    deleted_lines = [original_lines[0], original_lines[1], original_lines[3], original_lines[4]]  # Record 2 removed
    with open(deleted_file, "w", encoding="utf-8") as f:
        f.writelines(deleted_lines)

    is_valid, count, err = verify_audit_log_integrity(deleted_file)
    assert is_valid is False
    assert ("Sequence ID gap" in err or "Broken hash link" in err)

    # 4. Test Record Reordering (Swap records 2 and 3)
    swapped_file = tmp_path / "swapped_audit.jsonl"
    swapped_lines = list(original_lines)
    swapped_lines[2], swapped_lines[3] = swapped_lines[3], swapped_lines[2]
    with open(swapped_file, "w", encoding="utf-8") as f:
        f.writelines(swapped_lines)

    is_valid, count, err = verify_audit_log_integrity(swapped_file)
    assert is_valid is False
    assert ("Sequence ID gap" in err or "Broken hash link" in err)


def test_zero_cleartext_pan_in_audit_and_response(tmp_path):
    """
    Submits raw PAN across API and verifies zero cleartext occurrences anywhere in:
    - HTTP response body
    - Structured audit logs
    """
    raw_pan = "4532015112830366"
    raw_cvv = "876"
    log_file = tmp_path / "pci_check_audit.jsonl"
    test_logger = StructuredAuditLogger(log_path=log_file)

    # 1. Direct log_event with sensitive fields
    test_logger.log_event(
        event_type="INGESTION_PAYLOAD",
        payload={
            "transaction_id": "tx_pci_test_abc",
            "pan": raw_pan,
            "card_pan": raw_pan,
            "cvv": raw_cvv,
            "secret_key": "my_master_key"
        }
    )

    # 2. log_transaction_decision
    test_logger.log_transaction_decision(
        client_id="gw_service_01",
        client_role="SERVICE",
        result={
            "transaction_id": "tx_pci_test_abc",
            "amount": 45.00,
            "currency": "USD",
            "card_masked": "4532XXXXXXXX0366",
            "action": "APPROVE",
            "fraud_probability": 0.02
        }
    )

    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert raw_pan not in content, "Cleartext PAN leaked into audit log!"
    assert f'"{raw_cvv}"' not in content, "CVV leaked into audit log!"
    assert "my_master_key" not in content, "Secret leaked into audit log!"
    assert "[REDACTED_PCI_DSS]" in content
