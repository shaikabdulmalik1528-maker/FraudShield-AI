"""
FraudShield 3.0 Security Configuration & Role Definitions.
Defines role-based access control (RBAC), API key registry models,
and default security policies.
"""

import os
import hashlib
import secrets
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from pydantic import BaseModel, Field


class ClientRole(str, Enum):
    ADMIN = "ADMIN"        # Model reload, threshold updates, admin telemetry, rollback
    ANALYST = "ANALYST"    # Manual review queue, evidence inspection, drift metrics
    SERVICE = "SERVICE"    # Payment gateway / high-throughput scoring ingestion
    PARTNER = "PARTNER"    # External fintech/merchant partner sandbox access


class ApiKeyMetadata(BaseModel):
    key_id: str
    name: str
    role: ClientRole
    key_hash: str          # SHA-256(raw_key + salt)
    salt: str
    rate_limit_per_min: int = 6000
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None


class SecurityConfig:
    """Security settings, default salts, and API key store."""

    DEFAULT_SALT: str = os.getenv("FRAUDSHIELD_API_KEY_SALT", "fs3_sec_salt_98f4b238a")
    
    # Rate limits per minute by role
    RATE_LIMITS: Dict[ClientRole, int] = {
        ClientRole.SERVICE: 6000,   # 100 req/sec for payment ingestion
        ClientRole.PARTNER: 1200,   # 20 req/sec for partner sandbox testing
        ClientRole.ANALYST: 300,    # 5 req/sec for analysts
        ClientRole.ADMIN: 60        # 1 req/sec for administrative operations
    }


def hash_api_key(raw_key: str, salt: str = SecurityConfig.DEFAULT_SALT) -> str:
    """Computes salted SHA-256 hash of an API key for secure storage and comparison."""
    return hashlib.sha256((raw_key + salt).encode("utf-8")).hexdigest()
