"""
FraudShield 3.0 Streaming Feature Store Package.
Provides sliding-window aggregation, geo-spatial velocity calculation, and enrichment pipelines.
"""

import os
import logging
from typing import Optional

from backend.app.v3.feature_store.base import (
    BaseFeatureStore,
    WINDOW_1H_SECONDS,
    WINDOW_24H_SECONDS,
    WINDOW_7D_SECONDS,
    WINDOW_30D_SECONDS
)
from backend.app.v3.feature_store.schemas import (
    EnrichedFeatureVector,
    CardVelocityStats,
    MerchantVelocityStats,
    GeoLocation
)
from backend.app.v3.feature_store.geo import (
    calculate_haversine_distance,
    calculate_speed_kmh,
    evaluate_impossible_travel,
    DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.redis_store import RedisSlidingWindowStore, REDIS_AVAILABLE
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline

logger = logging.getLogger(__name__)


def get_feature_store(
    backend: str = "auto",
    redis_url: Optional[str] = None
) -> BaseFeatureStore:
    """
    Factory creating the appropriate feature store backend.
    - 'in_memory': Deterministic, thread-safe in-memory store for tests and offline processing.
    - 'redis': Redis-backed persistent store for high-throughput streaming environments.
    - 'auto': Attempts Redis connection if configured, gracefully falling back to in_memory.
    """
    selected_backend = backend.lower()
    url = redis_url or os.environ.get("FRAUDSHIELD_REDIS_URL")

    if selected_backend == "redis":
        return RedisSlidingWindowStore(redis_url=url)
    elif selected_backend == "in_memory":
        return InMemorySlidingWindowStore()
    elif selected_backend == "auto":
        if REDIS_AVAILABLE and url:
            try:
                import redis
                client = redis.from_url(url, socket_connect_timeout=0.5)
                client.ping()
                logger.info("Connected to Redis streaming feature store at %s", url)
                return RedisSlidingWindowStore(redis_client=client)
            except Exception as exc:
                logger.warning(
                    "Redis connection failed (%s); falling back to InMemorySlidingWindowStore",
                    exc
                )
        return InMemorySlidingWindowStore()
    else:
        raise ValueError(f"Unknown feature store backend: '{backend}'. Expected 'auto', 'redis', or 'in_memory'")


__all__ = [
    "BaseFeatureStore",
    "InMemorySlidingWindowStore",
    "RedisSlidingWindowStore",
    "StreamingFeaturePipeline",
    "EnrichedFeatureVector",
    "CardVelocityStats",
    "MerchantVelocityStats",
    "GeoLocation",
    "WINDOW_1H_SECONDS",
    "WINDOW_24H_SECONDS",
    "WINDOW_7D_SECONDS",
    "WINDOW_30D_SECONDS",
    "DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH",
    "calculate_haversine_distance",
    "calculate_speed_kmh",
    "evaluate_impossible_travel",
    "get_feature_store"
]
