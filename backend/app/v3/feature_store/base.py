"""
FraudShield 3.0 Feature Store Abstract Base Port.
Defines the interface for sliding-window velocity aggregations, idempotency, and state persistence.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from backend.app.v3.schemas.canonical import CanonicalTransaction
from backend.app.v3.feature_store.schemas import (
    CardVelocityStats,
    MerchantVelocityStats,
    GeoLocation
)

WINDOW_1H_SECONDS = 3600
WINDOW_24H_SECONDS = 86400
WINDOW_7D_SECONDS = 604800
WINDOW_30D_SECONDS = 2592000
DEFAULT_KEY_TTL_SECONDS = 31 * 86400
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 31 * 86400  # 31 days to safely cover 30-day sliding window (IDEMP-01)


class BaseFeatureStore(ABC):
    """
    Abstract interface for streaming feature store backends.
    Implementations must support concurrent updates, out-of-order event ingestion,
    sliding-window aggregations, and idempotency checks.
    """

    @abstractmethod
    def is_duplicate_transaction(self, transaction_id: str, merchant_id: Optional[str] = None) -> bool:
        """
        Checks whether transaction_id has already been processed.
        Returns True if duplicate, False otherwise. Supports optional merchant scoping (IDEMP-02).
        """
        pass

    @abstractmethod
    def record_transaction(self, tx: CanonicalTransaction) -> bool:
        """
        Persists transaction event into card, merchant, and geo sliding timelines.
        Returns True if accepted and recorded, False if rejected as duplicate.
        """
        pass

    @abstractmethod
    def get_card_velocity_stats(
        self,
        card_token: str,
        reference_time: datetime,
        current_amount: float,
        currency: str = "USD"
    ) -> CardVelocityStats:
        """
        Computes 1h, 24h, 7d, and 30d sliding window statistics for a card token
        strictly prior to reference_time, normalizing spend into base USD (CURR-01).
        """
        pass

    @abstractmethod
    def get_merchant_velocity_stats(
        self,
        merchant_id: str,
        reference_time: datetime
    ) -> MerchantVelocityStats:
        """
        Computes 1h and 24h sliding window statistics for a merchant
        strictly prior to reference_time.
        """
        pass

    @abstractmethod
    def get_last_known_location(self, card_token: str) -> Optional[GeoLocation]:
        """
        Retrieves the most recent physical location recorded for the card.
        """
        pass

    @abstractmethod
    def prune_expired(
        self,
        reference_time: Optional[datetime] = None,
        max_window_seconds: int = WINDOW_30D_SECONDS
    ) -> int:
        """
        Evicts events older than max_window_seconds to manage memory and freshness.
        Returns total number of pruned records.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Flushes all state (used for testing and maintenance)."""
        pass
