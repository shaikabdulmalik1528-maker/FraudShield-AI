"""
FraudShield 3.0 Sliding-Window Rate Limiter.
Provides thread-safe in-memory rate limiting per client key or IP address.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from fastapi import Request, HTTPException, status, Depends
from backend.app.v3.security.config import ApiKeyMetadata
from backend.app.v3.security.auth import get_current_client


class SlidingWindowRateLimiter:
    """
    Sliding-window counter rate limiter with 60-second resolution.
    Thread-safe implementation with write-time window pruning.
    """

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._client_timestamps: Dict[str, List[float]] = {}

    def is_allowed(self, client_id: str, max_requests: int) -> Tuple[bool, int, int]:
        """
        Determines whether client request is allowed.
        Returns (is_allowed, remaining_quota, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._client_timestamps.setdefault(client_id, [])
            
            # Prune timestamps older than window cutoff
            valid_ts = [t for t in timestamps if t > cutoff]
            self._client_timestamps[client_id] = valid_ts

            if len(valid_ts) >= max_requests:
                oldest_in_window = valid_ts[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now))
                return False, 0, retry_after

            # Record current request
            valid_ts.append(now)
            remaining = max(0, max_requests - len(valid_ts))
            return True, remaining, 0

    def clear(self):
        """Clears all client rate limit records (for testing)."""
        with self._lock:
            self._client_timestamps.clear()


# Global rate limiter instance
rate_limiter = SlidingWindowRateLimiter(window_seconds=60)


async def check_rate_limit(
    request: Request,
    client: ApiKeyMetadata = Depends(get_current_client)
) -> ApiKeyMetadata:
    """
    FastAPI dependency enforcing sliding-window rate limit based on client's role quota.
    """
    client_id = client.key_id
    max_quota = client.rate_limit_per_min

    allowed, remaining, retry_after = rate_limiter.is_allowed(client_id, max_quota)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Quota: {max_quota} req/min. Please retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    # Attach remaining quota info to request state
    request.state.rate_limit_remaining = remaining
    return client
