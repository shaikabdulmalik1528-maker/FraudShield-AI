"""
FraudShield 3.0 Authentication & Authorization Service.
Provides constant-time API key verification, key lifecycle management (registration,
rotation, revocation, expiry), failure telemetry, and FastAPI RBAC dependencies.
"""

import os
import time
import json
import secrets
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple, Any, Set
from fastapi import Header, HTTPException, Depends, status

from backend.app.v3.security.config import (
    ClientRole,
    ApiKeyMetadata,
    SecurityConfig,
    hash_api_key
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
REVOCATION_FILE = PROJECT_ROOT / "config" / "revoked_api_keys.json"


class ApiKeyManager:
    """
    Manages API key lifecycle and thread-safe validation.
    Stores only salted cryptographic hashes, never plaintext API keys.
    """

    def __init__(self, salt: Optional[str] = None):
        self.salt = salt or SecurityConfig.DEFAULT_SALT
        self._keys_by_id: Dict[str, ApiKeyMetadata] = {}
        self._hash_to_id: Dict[str, str] = {}
        self._revoked_hashes: Set[str] = set()
        
        # Telemetry counters
        self.auth_success_count: int = 0
        self.auth_failure_count: int = 0
        self.total_validation_latency_ns: int = 0

        self._seed_default_keys()
        self._load_persistent_revocations()

    def _seed_default_keys(self):
        """Seeds default keys from environment or generates standard development keys."""
        admin_key = os.getenv("FRAUDSHIELD_ADMIN_API_KEY", "fs3_admin_sec_key_2026_dev")
        service_key = os.getenv("FRAUDSHIELD_SERVICE_API_KEY", "fs3_service_gw_key_2026_dev")
        analyst_key = os.getenv("FRAUDSHIELD_ANALYST_API_KEY", "fs3_analyst_ui_key_2026_dev")
        partner_key = os.getenv("FRAUDSHIELD_PARTNER_API_KEY", "fs3_partner_sandbox_key_2026_dev")

        self.register_key("system_admin", ClientRole.ADMIN, raw_key=admin_key, key_id="key_admin_001")
        self.register_key("payment_gateway_service", ClientRole.SERVICE, raw_key=service_key, key_id="key_service_001")
        self.register_key("fraud_analyst_ops", ClientRole.ANALYST, raw_key=analyst_key, key_id="key_analyst_001")
        self.register_key("partner_sandbox_client", ClientRole.PARTNER, raw_key=partner_key, key_id="key_partner_001")

    def _load_persistent_revocations(self):
        """Loads revoked keys from environment, persistent disk file, and Redis."""
        # 1. From environment variable FRAUDSHIELD_REVOKED_API_KEYS
        revoked_env = os.getenv("FRAUDSHIELD_REVOKED_API_KEYS", "")
        if revoked_env:
            for item in revoked_env.split(","):
                item_clean = item.strip()
                if item_clean:
                    if len(item_clean) == 64 and all(c in "0123456789abcdefABCDEF" for c in item_clean):
                        self._revoked_hashes.add(item_clean.lower())
                    else:
                        self._revoked_hashes.add(hash_api_key(item_clean, self.salt))

        # 2. From persistent JSON file on disk
        if REVOCATION_FILE.exists():
            try:
                data = json.loads(REVOCATION_FILE.read_text(encoding="utf-8"))
                for entry in data.get("revoked_keys", []):
                    h = entry.get("key_hash")
                    if h:
                        self._revoked_hashes.add(h.lower())
            except Exception as e:
                logger.warning("Could not read revocation file %s: %s", REVOCATION_FILE, e)

        # 3. Synchronize with Redis shared set
        self._sync_redis_revocations()

    def _sync_redis_revocations(self):
        """Reads and writes revoked hashes to Redis shared set for multi-worker consistency."""
        redis_url = os.getenv("FRAUDSHIELD_REDIS_URL")
        if not redis_url:
            return
        try:
            import redis
            r = redis.Redis.from_url(redis_url, socket_timeout=0.20, decode_responses=True)
            redis_revoked = r.smembers("fs3:auth:revoked_hashes")
            if redis_revoked:
                self._revoked_hashes.update(redis_revoked)
            if self._revoked_hashes:
                r.sadd("fs3:auth:revoked_hashes", *self._revoked_hashes)
        except Exception:
            pass

    def _persist_revocation_record(self, key_id: str, key_hash: str, reason: str):
        """Persists a revoked hash to config/revoked_api_keys.json and Redis."""
        try:
            REVOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            existing = {"revoked_keys": []}
            if REVOCATION_FILE.exists():
                try:
                    existing = json.loads(REVOCATION_FILE.read_text(encoding="utf-8"))
                except Exception:
                    existing = {"revoked_keys": []}

            existing_hashes = {e.get("key_hash") for e in existing.get("revoked_keys", [])}
            if key_hash not in existing_hashes:
                existing.setdefault("revoked_keys", []).append({
                    "key_id": key_id,
                    "key_hash": key_hash,
                    "revoked_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason
                })
                REVOCATION_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to write persistent revocation record: %s", e)

        redis_url = os.getenv("FRAUDSHIELD_REDIS_URL")
        if redis_url:
            try:
                import redis
                r = redis.Redis.from_url(redis_url, socket_timeout=0.20, decode_responses=True)
                r.sadd("fs3:auth:revoked_hashes", key_hash)
            except Exception:
                pass

    def register_key(
        self,
        name: str,
        role: ClientRole,
        raw_key: Optional[str] = None,
        key_id: Optional[str] = None,
        ttl_days: Optional[int] = None
    ) -> Tuple[str, ApiKeyMetadata]:
        """
        Registers a new API key. Returns the plaintext raw_key once (for client distribution)
        and stores only the salted SHA-256 hash.
        """
        actual_raw_key = raw_key or f"fs3_{role.value.lower()}_{secrets.token_urlsafe(32)}"
        actual_key_id = key_id or f"key_{role.value.lower()}_{secrets.token_hex(6)}"
        
        expires_at = None
        if ttl_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

        k_hash = hash_api_key(actual_raw_key, self.salt)
        meta = ApiKeyMetadata(
            key_id=actual_key_id,
            name=name,
            role=role,
            key_hash=k_hash,
            salt=self.salt,
            rate_limit_per_min=SecurityConfig.RATE_LIMITS.get(role, 6000),
            is_active=True,
            expires_at=expires_at
        )

        self._keys_by_id[actual_key_id] = meta
        self._hash_to_id[k_hash] = actual_key_id
        logger.info("Registered API key %s (role=%s, key_id=%s)", name, role.value, actual_key_id)
        return actual_raw_key, meta

    def revoke_key(self, key_id: str, reason: str = "Administrative revocation") -> bool:
        """Revokes an existing API key immediately and persists across restarts and workers."""
        meta = self._keys_by_id.get(key_id)
        if not meta:
            return False
        meta.is_active = False
        meta.revoked_at = datetime.now(timezone.utc)
        self._revoked_hashes.add(meta.key_hash)
        self._persist_revocation_record(meta.key_id, meta.key_hash, reason)
        logger.warning("Revoked API key %s (%s)", key_id, meta.name)
        return True

    def revoke_raw_key(self, raw_key: str, key_id: Optional[str] = None, reason: str = "Key rotated or compromised") -> str:
        """Permanently revokes a raw key, computes salted hash, and persists across restarts."""
        k_hash = hash_api_key(raw_key, self.salt)
        self._revoked_hashes.add(k_hash)
        actual_id = key_id or self._hash_to_id.get(k_hash) or f"revoked_{secrets.token_hex(4)}"
        if k_hash in self._hash_to_id:
            kid = self._hash_to_id[k_hash]
            if kid in self._keys_by_id:
                self._keys_by_id[kid].is_active = False
                self._keys_by_id[kid].revoked_at = datetime.now(timezone.utc)
        self._persist_revocation_record(actual_id, k_hash, reason)
        logger.warning("Permanently revoked key hash %s... (key_id=%s)", k_hash[:8], actual_id)
        return k_hash

    def rotate_key(self, key_id: str, ttl_days: Optional[int] = None) -> Tuple[str, ApiKeyMetadata]:
        """Revokes the old key and generates a replacement key under the same identity and role."""
        old_meta = self._keys_by_id.get(key_id)
        if not old_meta:
            raise KeyError(f"Key ID {key_id} not found.")

        self.revoke_key(key_id, reason="Key rotation replacement")
        new_name = f"{old_meta.name}_rotated"
        return self.register_key(name=new_name, role=old_meta.role, ttl_days=ttl_days)

    def validate_key(self, raw_key: str) -> Optional[ApiKeyMetadata]:
        """
        Validates raw API key using constant-time hash comparison.
        Returns ApiKeyMetadata if valid and active, None otherwise.
        """
        t0 = time.perf_counter_ns()
        computed_hash = hash_api_key(raw_key, self.salt)

        # Immediate rejection of persistently revoked key hashes
        if computed_hash in self._revoked_hashes:
            dt_ns = time.perf_counter_ns() - t0
            self.total_validation_latency_ns += dt_ns
            self.auth_failure_count += 1
            logger.warning("Authentication rejected: API key has been permanently revoked.")
            return None

        matched_meta: Optional[ApiKeyMetadata] = None
        # Constant-time comparison across all registered keys to prevent timing leakage
        for stored_hash, k_id in self._hash_to_id.items():
            if secrets.compare_digest(computed_hash, stored_hash):
                candidate = self._keys_by_id.get(k_id)
                if candidate and candidate.is_active:
                    # Check expiry
                    if candidate.expires_at and datetime.now(timezone.utc) > candidate.expires_at:
                        logger.warning("API key %s has expired at %s", candidate.key_id, candidate.expires_at)
                        continue
                    matched_meta = candidate

        dt_ns = time.perf_counter_ns() - t0
        self.total_validation_latency_ns += dt_ns

        if matched_meta:
            self.auth_success_count += 1
        else:
            self.auth_failure_count += 1

        return matched_meta

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides operational metrics for authentication verification."""
        total_validations = self.auth_success_count + self.auth_failure_count
        avg_lat_us = (
            (self.total_validation_latency_ns / max(total_validations, 1)) / 1_000.0
        )
        return {
            "active_keys_count": sum(1 for k in self._keys_by_id.values() if k.is_active),
            "auth_success_count": self.auth_success_count,
            "auth_failure_count": self.auth_failure_count,
            "avg_validation_latency_us": round(avg_lat_us, 2)
        }


# Global singleton key manager
api_key_manager = ApiKeyManager()


# --- FastAPI RBAC Dependencies ---

async def get_current_client(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
) -> ApiKeyMetadata:
    """
    FastAPI dependency extracting client credentials from `X-API-Key` header
    or Bearer token. Enforces constant-time validation.
    """
    token_str: Optional[str] = None
    if x_api_key:
        token_str = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token_str = authorization[7:].strip()

    if not token_str:
        api_key_manager.auth_failure_count += 1
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials. Provide 'X-API-Key' header or Bearer token.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    client_meta = api_key_manager.validate_key(token_str)
    if not client_meta:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked API key.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return client_meta


def require_role(allowed_roles: List[ClientRole]):
    """
    Factory creating a FastAPI dependency that verifies whether the client
    has one of the authorized roles.
    """
    async def role_checker(client: ApiKeyMetadata = Depends(get_current_client)) -> ApiKeyMetadata:
        if client.role not in allowed_roles:
            logger.warning(
                "Access denied for client %s (%s). Required: %s, Actual: %s",
                client.key_id, client.name, [r.value for r in allowed_roles], client.role.value
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Role '{client.role.value}' cannot access this endpoint."
            )
        return client

    return role_checker
