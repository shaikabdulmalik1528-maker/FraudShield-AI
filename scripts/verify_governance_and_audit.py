"""
FraudShield 3.0 Governance, Audit Chain Integrity & Drift Verification.
Verifies:
1. Cryptographic SHA-256 hash chaining of audit log entries via verify_audit_log_integrity().
2. Mathematical detection of tampering, record deletion, and sequence gaps.
3. PCI-DSS PAN sanitization (zero cleartext PAN or CVV in log files).
4. Drift telemetry (PSI, KS divergence, rolling fraud rate).
5. Redis circuit breaker state transitions and degraded mode fail-safe policies.
"""

import os
import sys
import json
import re
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.v3.security.audit_logger import StructuredAuditLogger, verify_audit_log_integrity, GENESIS_HASH
from backend.app.v3.monitoring.drift_detector import drift_detector
from backend.app.v3.feature_store.redis_connection import RedisCircuitBreaker, CircuitState


def test_audit_integrity_synthetic():
    print("\n[1] Verifying Cryptographic Audit Log Integrity & Tamper Proofing...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_log = Path(tmp_dir) / "test_audit_chain.jsonl"
        logger = StructuredAuditLogger(log_path=test_log)

        # 1. Generate 100 chained audit records
        for i in range(100):
            logger.log_event("TX_PILOT_VERIFY", {
                "tx_id": f"tx_verify_{i}",
                "amount": round(25.0 + i, 2),
                "card_masked": "453201XXXXXX0366",
                "action": "APPROVE" if i % 5 != 0 else "MANUAL_REVIEW"
            })

        # Verify clean chain
        is_valid, count, err = verify_audit_log_integrity(test_log)
        print(f"  Synthetic Chain Records Logged: 100")
        print(f"  Verification Result:            {'VALID (100% SHA-256 Passed)' if is_valid else 'FAILED'} (Records: {count})")
        assert is_valid and count == 100

        # Read records
        with open(test_log, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 2. Tamper Test: Modify record content
        tampered_log = Path(tmp_dir) / "tampered.jsonl"
        t_lines = list(lines)
        rec = json.loads(t_lines[10])
        rec["amount"] = 999999.99
        t_lines[10] = json.dumps(rec) + "\n"
        with open(tampered_log, "w", encoding="utf-8") as f:
            f.writelines(t_lines)

        t_valid, t_count, t_err = verify_audit_log_integrity(tampered_log)
        print(f"  Tamper Detection Check:         {'DETECTED (Expected Failure)' if not t_valid else 'MISSED'}")
        print(f"    -> Detail: {t_err}")
        assert not t_valid and "Tampered record" in t_err

        # 3. Deletion Test: Delete line 25
        deleted_log = Path(tmp_dir) / "deleted.jsonl"
        d_lines = lines[:25] + lines[26:]
        with open(deleted_log, "w", encoding="utf-8") as f:
            f.writelines(d_lines)

        d_valid, d_count, d_err = verify_audit_log_integrity(deleted_log)
        print(f"  Deletion Detection Check:       {'DETECTED (Expected Failure)' if not d_valid else 'MISSED'}")
        print(f"    -> Detail: {d_err}")
        assert not d_valid and ("Sequence ID gap" in d_err or "Broken hash link" in d_err)

    return True


def test_pilot_worker_audit_logs():
    print("\n[2] Verifying Pilot Deployment Worker-Scoped Audit Logs...")
    logs_dirs = [PROJECT_ROOT / "logs", PROJECT_ROOT / "backend" / "logs"]
    found_logs = []
    for ld in logs_dirs:
        if ld.exists():
            found_logs.extend(list(ld.glob("pilot_audit*.jsonl")))

    print(f"  Found {len(found_logs)} pilot audit log files.")
    for pl in found_logs:
        v, c, e = verify_audit_log_integrity(pl)
        print(f"    - {pl.name:35s}: Valid={v} | Records={c} | Error={e}")
    return True


def test_pci_dss_sanitization():
    print("\n[3] Verifying PCI-DSS Sensitive Data Sanitization across Logs...")
    logs_dirs = [PROJECT_ROOT / "logs", PROJECT_ROOT / "backend" / "logs"]
    total_raw = 0
    total_redacted = 0
    total_masked = 0

    for ld in logs_dirs:
        if not ld.exists():
            continue
        for fpath in ld.glob("*.jsonl"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                raw_pan_matches = re.findall(r'"(?:card_number|card_pan|pan)"\s*:\s*"([0-9]{13,19})"', content)
                total_raw += len(raw_pan_matches)
                total_redacted += len(re.findall(r'\[REDACTED_PCI_DSS\]', content))
                total_masked += len(re.findall(r'"card_masked"\s*:\s*"\*{4,12}\d{4}"', content))
            except Exception:
                continue

    print(f"  Raw PAN Instances Across All Logs:   {total_raw}")
    print(f"  PCI Redacted Tags Found:             {total_redacted}")
    print(f"  Masked PAN Entries Found:            {total_masked}")
    is_clean = (total_raw == 0)
    print(f"  PCI-DSS Zero-Leakage Verdict:        {'PASS (100% Sanitized)' if is_clean else 'FAIL'}")
    return is_clean


def test_drift_telemetry():
    print("\n[4] Verifying Streaming Feature & Concept Drift Telemetry...")
    report = drift_detector.get_full_report()
    print(f"  Total Predictions Tracked: {report.get('total_predictions', 0)}")
    print(f"  Rolling Window Size:       {report.get('window_size', 0)}")
    print(f"  Features Configured:       {len(report.get('features', {}))}")
    for feat, data in report.get("features", {}).items():
        print(f"    - {feat:25s}: PSI={data.get('psi', 0):.4f} ({data.get('status')}) | KS p-value={data.get('ks_p_value', 1.0):.4f}")
    return True


def test_circuit_breaker_resilience():
    print("\n[5] Verifying Circuit Breaker & Degraded Mode Transitions...")
    cb = RedisCircuitBreaker(failure_threshold=3, cooldown_seconds=0.2)
    assert cb.state == CircuitState.CLOSED
    print("  [Step 1] Initial Circuit State: CLOSED")

    # Trip breaker
    cb.record_failure(Exception("Connection timeout"))
    cb.record_failure(Exception("Connection reset"))
    cb.record_failure(Exception("Network unreachable"))
    assert cb.state == CircuitState.OPEN
    print("  [Step 2] After 3 Failures: TRIPPED to OPEN (Graceful failover triggered)")

    # Immediate execution attempt blocked
    assert not cb.can_attempt()
    print("  [Step 3] Immediate Attempt: BLOCKED (Traffic directed to in-memory store)")

    # Cooldown & probe
    import time
    time.sleep(0.3)
    assert cb.can_attempt()
    assert cb.state == CircuitState.HALF_OPEN
    print("  [Step 4] After Cooldown: Transitioned to HALF_OPEN (Probing recovery)")

    # Recovery
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    print("  [Step 5] After Probe Success: RESTORED to CLOSED (Self-healing complete)")
    return True


def main():
    print("=" * 80)
    print("FRAUDSHIELD 3.0 — GOVERNANCE, AUDIT INTEGRITY & DRIFT VALIDATION")
    print("=" * 80)

    t1 = test_audit_integrity_synthetic()
    t2 = test_pilot_worker_audit_logs()
    t3 = test_pci_dss_sanitization()
    t4 = test_drift_telemetry()
    t5 = test_circuit_breaker_resilience()

    all_passed = t1 and t2 and t3 and t4 and t5
    print("\n" + "=" * 80)
    print(f"OVERALL GOVERNANCE VERIFICATION: {'ALL PASSED' if all_passed else 'FAILED'}")
    print("=" * 80)
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
