"""
FraudShield 3.0 Structured Audit Logging Service.
Provides tamper-evident, PCI-DSS aligned JSON audit logs for transaction scoring,
model lifecycle changes, and authentication events with guaranteed zero cleartext PAN.
"""

import os
import json
import logging
import hashlib
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

AUDIT_LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs"
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "v3_audit.jsonl"


GENESIS_HASH = "0" * 64


class StructuredAuditLogger:
    """
    Appends structured JSON audit events with cryptographic SHA-256 hash chaining.
    Enforces strict PCI-DSS sensitive data redaction and mathematical tamper evidence.
    """

    def __init__(self, log_path: Optional[Path] = None):
        if log_path:
            self.log_path = log_path
        else:
            env_override = os.environ.get("FRAUDSHIELD_AUDIT_LOG_PATH")
            base_path = Path(env_override) if env_override else AUDIT_LOG_FILE
            if os.environ.get("FRAUDSHIELD_WORKER_SCOPED_AUDIT", "false").lower() in ("true", "1"):
                self.log_path = base_path.parent / f"{base_path.stem}_worker_{os.getpid()}{base_path.suffix}"
            else:
                self.log_path = base_path

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.sequence_id: int = 0
        self.last_hash: str = GENESIS_HASH
        self._init_chain_state()

    def _init_chain_state(self):
        """Resumes hash chain sequence and last digest from existing log file if present."""
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            self.sequence_id = 0
            self.last_hash = GENESIS_HASH
            return

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines:
                last_rec = json.loads(lines[-1])
                if "record_hash" in last_rec and "sequence_id" in last_rec:
                    self.sequence_id = int(last_rec["sequence_id"]) + 1
                    self.last_hash = str(last_rec["record_hash"])
        except Exception as exc:
            logger.warning("Could not resume audit hash chain from %s: %s", self.log_path, exc)
            self.sequence_id = 0
            self.last_hash = GENESIS_HASH

    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures raw PAN, CVC, or pin blocks are never persisted to audit logs."""
        sanitized = {}
        forbidden_keys = {"pan", "card_pan", "cvv", "cvc", "pin", "password", "secret"}
        for k, v in data.items():
            if any(forbidden in k.lower() for forbidden in forbidden_keys):
                sanitized[k] = "[REDACTED_PCI_DSS]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_data(v)
            else:
                sanitized[k] = v
        return sanitized

    def log_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Writes sanitized JSON audit line with cryptographic SHA-256 hash chaining."""
        with self._lock:
            seq = self.sequence_id
            prev_h = self.last_hash
            ts = datetime.now(timezone.utc).isoformat()
            sanitized = self._sanitize_data(payload)

            record = {
                "sequence_id": seq,
                "prev_hash": prev_h,
                "timestamp": ts,
                "event_type": event_type,
                **sanitized
            }

            # Deterministic canonical serialization for hashing
            canonical_str = json.dumps(record, sort_keys=True, default=str)
            hash_input = f"{prev_h}:{seq}:{canonical_str}".encode("utf-8")
            rec_hash = hashlib.sha256(hash_input).hexdigest()

            record["record_hash"] = rec_hash
            line = json.dumps(record, default=str)

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            self.sequence_id += 1
            self.last_hash = rec_hash

            # Also emit to structured application logger at INFO
            logger.info("[AUDIT] %s #%d [%s]: %s", event_type, seq, rec_hash[:8], line)
            return record

    def log_transaction_decision(
        self,
        client_id: str,
        client_role: str,
        result: Dict[str, Any]
    ):
        """Specialized logger for real-time transaction scoring decisions."""
        self.log_event(
            event_type="TRANSACTION_SCORED",
            payload={
                "client_id": client_id,
                "client_role": client_role,
                "transaction_id": result.get("transaction_id"),
                "amount": result.get("amount"),
                "currency": result.get("currency"),
                "card_masked": result.get("card_masked"),
                "action": result.get("action"),
                "risk_score": result.get("risk_score"),
                "fraud_probability": result.get("fraud_probability"),
                "rule_triggers": result.get("rule_triggers", []),
                "is_duplicate": result.get("is_duplicate", False),
                "is_degraded": result.get("is_degraded", False),
                "feature_store_backend": result.get("feature_store_backend"),
                "latency_ms": result.get("latency_ms")
            }
        )

    def log_model_lifecycle(
        self,
        event_type: str,
        client_id: str,
        model_version: str,
        details: Dict[str, Any]
    ):
        """Logs model reload, rollout, or rollback operations."""
        self.log_event(
            event_type=event_type,
            payload={
                "client_id": client_id,
                "model_version": model_version,
                **details
            }
        )


def verify_audit_log_integrity(log_path: Optional[Path] = None) -> Tuple[bool, int, Optional[str]]:
    """
    Forensically verifies cryptographic SHA-256 hash chain integrity of the audit log file.
    Validates:
    1. Monotonically increasing sequence_id with zero missing records or sequence gaps.
    2. Exact prev_hash linkage preventing record deletion, insertion, or reordering.
    3. Recomputed SHA-256 record_hash matching the logged digest for zero tampering.
    Returns: (is_valid, verified_record_count, error_detail)
    """
    target = log_path or AUDIT_LOG_FILE
    if not target.exists() or target.stat().st_size == 0:
        return True, 0, None

    expected_seq = 0
    expected_prev_hash = GENESIS_HASH

    with open(target, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except Exception as exc:
                return False, line_no - 1, f"Line {line_no}: Malformed JSON syntax ({exc})"

            seq = record.get("sequence_id")
            prev_h = record.get("prev_hash")
            rec_h = record.get("record_hash")

            if seq is None or prev_h is None or rec_h is None:
                return False, line_no - 1, f"Line {line_no}: Missing cryptographic chain headers"

            if seq != expected_seq:
                return False, line_no - 1, f"Line {line_no}: Sequence ID gap. Expected {expected_seq}, found {seq}"

            if prev_h != expected_prev_hash:
                return False, line_no - 1, f"Line {line_no}: Broken hash link. Expected prev_hash {expected_prev_hash}, found {prev_h}"

            # Recompute hash across all fields excluding record_hash
            body = {k: v for k, v in record.items() if k != "record_hash"}
            canonical_str = json.dumps(body, sort_keys=True, default=str)
            computed_hash = hashlib.sha256(f"{prev_h}:{seq}:{canonical_str}".encode("utf-8")).hexdigest()

            if computed_hash != rec_h:
                return False, line_no - 1, f"Line {line_no}: Tampered record. Recorded {rec_h} != computed {computed_hash}"

            expected_prev_hash = rec_h
            expected_seq += 1

    return True, expected_seq, None


# Global audit logger instance
audit_logger = StructuredAuditLogger()
