"""
FraudShield 3.0 Production Redis Connection Manager & Circuit Breaker (RESIL-01).
Provides high-performance connection pooling, health checking, and automatic
circuit breaker failover to ensure the serving pipeline remains resilient even
when the Redis cluster encounters transient failures or network partitions.
"""

import os
import time
import logging
from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: Redis healthy
    OPEN = "OPEN"            # Tripped: Redis failed, bypass directly to fallback
    HALF_OPEN = "HALF_OPEN"  # Probe: testing Redis recovery


@dataclass
class RedisConfig:
    url: str = os.environ.get("FRAUDSHIELD_REDIS_URL", "redis://localhost:6379/0")
    max_connections: int = 50
    socket_timeout: float = 1.0
    socket_connect_timeout: float = 0.2
    retry_on_timeout: bool = True
    prefix: str = "fs3"


class RedisCircuitBreaker:
    """
    Implements the Circuit Breaker pattern for Redis communication.
    Transitions:
      CLOSED --(failure_threshold failures)--> OPEN
      OPEN --(cooldown elapsed)--> HALF_OPEN
      HALF_OPEN --(success)--> CLOSED
      HALF_OPEN --(failure)--> OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 15.0
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()

    def can_attempt(self) -> bool:
        """Determines whether a Redis command should be attempted."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            now = time.time()
            if now - self.last_failure_time >= self.cooldown_seconds:
                logger.info("Redis circuit breaker transitioning from OPEN to HALF_OPEN (probing recovery)...")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False

        # HALF_OPEN: Allow single trial
        return True

    def can_execute(self) -> bool:
        """Alias for can_attempt."""
        return self.can_attempt()

    def record_success(self) -> None:
        """Records a successful Redis operation, restoring circuit to CLOSED."""
        if self.state != CircuitState.CLOSED:
            logger.info("Redis recovered successfully. Circuit breaker restored to CLOSED.")
        self.state = CircuitState.CLOSED
        self.failure_count = 0

    def record_failure(self, exc: Optional[Exception] = None) -> None:
        """Records a Redis failure, tripping circuit if threshold is reached."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.error(
                    "Redis circuit breaker TRIPPED to OPEN after %d consecutive failures. "
                    "Failing over to in-memory fallback store. Root cause: %s",
                    self.failure_count, exc
                )
            self.state = CircuitState.OPEN
            self.last_state_change = self.last_failure_time


class RedisManager:
    """
    Manages Redis connection pooling, health checks, and circuit-breaker telemetry.
    """

    def __init__(self, config: Optional[RedisConfig] = None, client: Optional[Any] = None):
        self.config = config or RedisConfig()
        self.circuit_breaker = RedisCircuitBreaker()
        self._pool: Optional[Any] = None
        self._client: Optional[Any] = client

        if self._client is None and REDIS_AVAILABLE:
            self._init_pool()

    def _init_pool(self) -> None:
        try:
            self._pool = redis.ConnectionPool.from_url(
                self.config.url,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                decode_responses=True
            )
            self._client = redis.Redis(connection_pool=self._pool)
        except Exception as exc:
            logger.warning("Could not initialize Redis connection pool (%s); running in fallback mode", exc)
            self._client = None
            self.circuit_breaker.record_failure(exc)

    def get_client(self) -> Optional[Any]:
        """Returns the Redis client if circuit is not OPEN, else None."""
        if not self.circuit_breaker.can_attempt():
            return None
        return self._client

    def ping(self) -> bool:
        """Pings Redis to test connectivity and updates circuit breaker."""
        if self._client is None:
            return False
        try:
            res = self._client.ping()
            if res:
                self.circuit_breaker.record_success()
                return True
            return False
        except Exception as exc:
            self.circuit_breaker.record_failure(exc)
            return False

    def get_telemetry(self) -> dict:
        """Returns status telemetry for health/monitoring endpoints."""
        is_healthy = self.ping() if self.circuit_breaker.can_attempt() else False
        return {
            "circuit_state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker.failure_count,
            "is_available": is_healthy,
            "backend": "redis" if is_healthy else "in_memory_fallback"
        }
