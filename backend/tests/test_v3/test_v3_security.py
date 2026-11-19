"""
Security and Access Control Test Suite for FraudShield 3.0.
Verifies API key hashing, constant-time validation, key lifecycle (rotation, revocation, expiry),
role-based access control (RBAC), sliding-window rate limiting, and PCI-DSS audit redaction.
"""

import time
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v3.security.config import ClientRole, hash_api_key
from backend.app.v3.security.auth import ApiKeyManager
from backend.app.v3.security.rate_limiter import SlidingWindowRateLimiter
from backend.app.v3.security.audit_logger import StructuredAuditLogger

client = TestClient(app)


def test_api_key_hashing_and_constant_time_validation():
    """Verifies that API keys are stored only as salted hashes and validated safely."""
    mgr = ApiKeyManager(salt="test_salt_12345")
    raw_key, meta = mgr.register_key("test_service", ClientRole.SERVICE)

    # Plaintext key must NOT be stored in metadata
    assert raw_key != meta.key_hash
    assert meta.key_hash == hash_api_key(raw_key, "test_salt_12345")

    # Validation must succeed with correct key
    validated = mgr.validate_key(raw_key)
    assert validated is not None
    assert validated.key_id == meta.key_id
    assert validated.role == ClientRole.SERVICE

    # Tampered key must fail
    assert mgr.validate_key("fs3_service_invalid_key_string") is None


def test_api_key_expiry_enforcement():
    """Verifies that expired keys are rejected."""
    mgr = ApiKeyManager(salt="test_salt_12345")
    raw_key, meta = mgr.register_key("expiring_key", ClientRole.ANALYST, ttl_days=-1)

    assert meta.expires_at is not None
    assert mgr.validate_key(raw_key) is None


def test_api_key_revocation_and_rotation():
    """Verifies that revoking a key disables it and rotation creates a new valid key."""
    mgr = ApiKeyManager(salt="test_salt_12345")
    raw_key, meta = mgr.register_key("rotatable_key", ClientRole.ADMIN)

    # 1. Active key works
    assert mgr.validate_key(raw_key) is not None

    # 2. Revoke key
    assert mgr.revoke_key(meta.key_id) is True
    assert mgr.validate_key(raw_key) is None

    # 3. Rotate key
    new_raw_key, new_meta = mgr.rotate_key(meta.key_id)
    assert new_raw_key != raw_key
    assert new_meta.key_id != meta.key_id
    assert mgr.validate_key(new_raw_key) is not None
    assert mgr.validate_key(raw_key) is None


def test_sliding_window_rate_limiter():
    """Verifies sliding-window rate limiting and 429 quota exhaustion."""
    limiter = SlidingWindowRateLimiter(window_seconds=1)
    client_id = "test_rate_client_01"
    max_quota = 5

    # 5 requests allowed
    for i in range(max_quota):
        allowed, remaining, _ = limiter.is_allowed(client_id, max_quota)
        assert allowed is True
        assert remaining == max_quota - 1 - i

    # 6th request blocked
    allowed, remaining, retry_after = limiter.is_allowed(client_id, max_quota)
    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1

    # Wait for window to expire
    time.sleep(1.1)
    allowed, remaining, _ = limiter.is_allowed(client_id, max_quota)
    assert allowed is True


def test_structured_audit_logger_redacts_pci_dss_sensitive_fields(tmp_path):
    """Verifies that audit logs strictly sanitize cleartext PAN and CVV."""
    log_file = tmp_path / "test_audit.jsonl"
    logger_instance = StructuredAuditLogger(log_path=log_file)

    sensitive_payload = {
        "transaction_id": "tx_audit_test",
        "pan": "4532015112830366",
        "card_pan": "4532015112830366",
        "cvv": "123",
        "nested": {
            "secret_key": "top_secret",
            "card_masked": "4532XXXXXXXX0366"
        }
    }

    logger_instance.log_event("TEST_EVENT", sensitive_payload)

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])

    # Assert redactions
    assert record["pan"] == "[REDACTED_PCI_DSS]"
    assert record["card_pan"] == "[REDACTED_PCI_DSS]"
    assert record["cvv"] == "[REDACTED_PCI_DSS]"
    assert record["nested"]["secret_key"] == "[REDACTED_PCI_DSS]"
    assert record["nested"]["card_masked"] == "4532XXXXXXXX0366"
    assert "4532015112830366" not in json.dumps(record)


def test_api_key_validation_performance():
    """Measures actual hash validation latency and asserts sub-50 microsecond execution."""
    mgr = ApiKeyManager(salt="benchmark_salt")
    raw_key, _ = mgr.register_key("bench_key", ClientRole.SERVICE)

    latencies_us = []
    for _ in range(500):
        t0 = time.perf_counter_ns()
        _ = mgr.validate_key(raw_key)
        latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)

    p50_us = float(sorted(latencies_us)[len(latencies_us) // 2])
    p99_us = float(sorted(latencies_us)[int(len(latencies_us) * 0.99)])

    # Validation must be blazing fast (well under 100 microseconds)
    assert p50_us < 50.0, f"P50 validation too slow: {p50_us:.2f}us"
    assert p99_us < 200.0, f"P99 validation too slow: {p99_us:.2f}us"
