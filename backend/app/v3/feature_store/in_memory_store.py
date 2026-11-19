"""
FraudShield 3.0 Thread-Safe In-Memory Sliding Window Feature Store.
Implements BaseFeatureStore for low-latency testing, standalone execution, and offline environments.
Supports out-of-order event insertion via sorted timelines, idempotency, and TTL eviction.
"""

import math
import bisect
import threading
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from backend.app.v3.schemas.canonical import CanonicalTransaction, PaymentChannel
from backend.app.v3.feature_store.base import (
    BaseFeatureStore,
    WINDOW_1H_SECONDS,
    WINDOW_24H_SECONDS,
    WINDOW_7D_SECONDS,
    WINDOW_30D_SECONDS
)
from backend.app.v3.feature_store.schemas import (
    CardVelocityStats,
    MerchantVelocityStats,
    GeoLocation
)
from backend.app.v3.feature_store.currency import (
    BaseCurrencyConverter,
    default_currency_converter
)


class InMemorySlidingWindowStore(BaseFeatureStore):
    """
    In-memory, thread-safe implementation of the streaming feature store.
    Utilizes sorted timelines and bisect lookups to guarantee correct sliding window
    aggregations even when events arrive out-of-order.
    Normalizes all monetary spend sums and baselines to base USD (CURR-01).
    """

    def __init__(self, currency_converter: Optional[BaseCurrencyConverter] = None):
        self._lock = threading.RLock()
        self.currency_converter = currency_converter or default_currency_converter
        # card_token -> list of (epoch, amount_usd, tx_id) sorted by epoch
        self._card_timelines: Dict[str, List[Tuple[float, float, str]]] = defaultdict(list)
        # merchant_id -> list of (epoch, card_token, tx_id) sorted by epoch
        self._merchant_timelines: Dict[str, List[Tuple[float, str, str]]] = defaultdict(list)
        # tx_id and f"{merchant_id}:{tx_id}" -> ingestion epoch (idempotency registry)
        self._seen_tx_ids: Dict[str, float] = {}
        # card_token -> latest GeoLocation
        self._last_locations: Dict[str, GeoLocation] = {}

    def is_duplicate_transaction(self, transaction_id: str, merchant_id: Optional[str] = None) -> bool:
        with self._lock:
            if merchant_id:
                scoped_key = f"{merchant_id}:{transaction_id}"
                if scoped_key in self._seen_tx_ids:
                    return True
            return transaction_id in self._seen_tx_ids

    def record_transaction(self, tx: CanonicalTransaction) -> bool:
        with self._lock:
            scoped_key = f"{tx.merchant_id}:{tx.transaction_id}"
            if tx.transaction_id in self._seen_tx_ids or scoped_key in self._seen_tx_ids:
                return False

            epoch = tx.timestamp.timestamp()
            self._seen_tx_ids[tx.transaction_id] = epoch
            self._seen_tx_ids[scoped_key] = epoch

            # Normalize amount to base USD before recording in timeline (CURR-01)
            amount_usd = self.currency_converter.convert_to_usd(float(tx.amount), tx.currency)

            # Insert into card timeline maintaining sorted order by epoch
            card_entry = (epoch, amount_usd, tx.transaction_id)
            bisect.insort(self._card_timelines[tx.card_pan_token], card_entry)

            # Insert into merchant timeline maintaining sorted order by epoch
            merch_entry = (epoch, tx.card_pan_token, tx.transaction_id)
            bisect.insort(self._merchant_timelines[tx.merchant_id], merch_entry)

            # Update last known physical location if applicable
            if (
                tx.latitude is not None
                and tx.longitude is not None
                and tx.channel not in (PaymentChannel.ECOMMERCE, PaymentChannel.MOTO)
            ):
                current_last = self._last_locations.get(tx.card_pan_token)
                if current_last is None or tx.timestamp >= current_last.timestamp:
                    self._last_locations[tx.card_pan_token] = GeoLocation(
                        latitude=tx.latitude,
                        longitude=tx.longitude,
                        timestamp=tx.timestamp
                    )

            return True

    def get_card_velocity_stats(
        self,
        card_token: str,
        reference_time: datetime,
        current_amount: float,
        currency: str = "USD"
    ) -> CardVelocityStats:
        ref_epoch = reference_time.timestamp()
        current_amount_usd = self.currency_converter.convert_to_usd(current_amount, currency)

        with self._lock:
            timeline = self._card_timelines.get(card_token, [])
            if not timeline:
                return CardVelocityStats(
                    tx_count_1h=0,
                    tx_count_24h=0,
                    tx_count_7d=0,
                    tx_count_30d=0,
                    amount_sum_1h=0.0,
                    amount_sum_24h=0.0,
                    amount_sum_7d=0.0,
                    amount_mean_30d=0.0,
                    amount_std_30d=0.0,
                    amount_ratio_30d=1.0,
                    amount_zscore_30d=0.0
                )

            # Slicing up to reference_time (strictly prior to current event)
            idx_end = bisect.bisect_left(timeline, (ref_epoch, -math.inf, ""))
            prior_events = timeline[:idx_end]

            if not prior_events:
                return CardVelocityStats(
                    tx_count_1h=0,
                    tx_count_24h=0,
                    tx_count_7d=0,
                    tx_count_30d=0,
                    amount_sum_1h=0.0,
                    amount_sum_24h=0.0,
                    amount_sum_7d=0.0,
                    amount_mean_30d=0.0,
                    amount_std_30d=0.0,
                    amount_ratio_30d=1.0,
                    amount_zscore_30d=0.0
                )

            # Window thresholds
            t_1h = ref_epoch - WINDOW_1H_SECONDS
            t_24h = ref_epoch - WINDOW_24H_SECONDS
            t_7d = ref_epoch - WINDOW_7D_SECONDS
            t_30d = ref_epoch - WINDOW_30D_SECONDS

            # Binary search start indices
            idx_1h = bisect.bisect_left(prior_events, (t_1h, -math.inf, ""))
            idx_24h = bisect.bisect_left(prior_events, (t_24h, -math.inf, ""))
            idx_7d = bisect.bisect_left(prior_events, (t_7d, -math.inf, ""))
            idx_30d = bisect.bisect_left(prior_events, (t_30d, -math.inf, ""))

            events_1h = prior_events[idx_1h:]
            events_24h = prior_events[idx_24h:]
            events_7d = prior_events[idx_7d:]
            events_30d = prior_events[idx_30d:]

            count_1h = len(events_1h)
            count_24h = len(events_24h)
            count_7d = len(events_7d)
            count_30d = len(events_30d)

            sum_1h = round(sum(e[1] for e in events_1h), 2)
            sum_24h = round(sum(e[1] for e in events_24h), 2)
            sum_7d = round(sum(e[1] for e in events_7d), 2)

            # 30-day baseline statistics (all in base USD)
            if count_30d > 0:
                amounts_30d = [e[1] for e in events_30d]
                mean_30d = round(sum(amounts_30d) / count_30d, 2)
                variance = sum((x - mean_30d) ** 2 for x in amounts_30d) / count_30d
                std_30d = round(math.sqrt(variance), 2)
                ratio_30d = round(current_amount_usd / max(mean_30d, 0.01), 3)
                zscore_30d = round((current_amount_usd - mean_30d) / std_30d, 3) if std_30d > 1e-4 else 0.0
            else:
                mean_30d = 0.0
                std_30d = 0.0
                ratio_30d = 1.0
                zscore_30d = 0.0

            return CardVelocityStats(
                tx_count_1h=count_1h,
                tx_count_24h=count_24h,
                tx_count_7d=count_7d,
                tx_count_30d=count_30d,
                amount_sum_1h=sum_1h,
                amount_sum_24h=sum_24h,
                amount_sum_7d=sum_7d,
                amount_mean_30d=mean_30d,
                amount_std_30d=std_30d,
                amount_ratio_30d=ratio_30d,
                amount_zscore_30d=zscore_30d
            )

    def get_merchant_velocity_stats(
        self,
        merchant_id: str,
        reference_time: datetime
    ) -> MerchantVelocityStats:
        ref_epoch = reference_time.timestamp()

        with self._lock:
            timeline = self._merchant_timelines.get(merchant_id, [])
            if not timeline:
                return MerchantVelocityStats(tx_count_1h=0, tx_count_24h=0, distinct_cards_1h=0)

            idx_end = bisect.bisect_left(timeline, (ref_epoch, "", ""))
            prior_events = timeline[:idx_end]

            if not prior_events:
                return MerchantVelocityStats(tx_count_1h=0, tx_count_24h=0, distinct_cards_1h=0)

            t_1h = ref_epoch - WINDOW_1H_SECONDS
            t_24h = ref_epoch - WINDOW_24H_SECONDS

            idx_1h = bisect.bisect_left(prior_events, (t_1h, "", ""))
            idx_24h = bisect.bisect_left(prior_events, (t_24h, "", ""))

            events_1h = prior_events[idx_1h:]
            events_24h = prior_events[idx_24h:]

            count_1h = len(events_1h)
            count_24h = len(events_24h)
            distinct_cards_1h = len({e[1] for e in events_1h})

            return MerchantVelocityStats(
                tx_count_1h=count_1h,
                tx_count_24h=count_24h,
                distinct_cards_1h=distinct_cards_1h
            )

    def get_last_known_location(self, card_token: str) -> Optional[GeoLocation]:
        with self._lock:
            return self._last_locations.get(card_token)

    def prune_expired(
        self,
        reference_time: Optional[datetime] = None,
        max_window_seconds: int = WINDOW_30D_SECONDS
    ) -> int:
        now_epoch = (reference_time or datetime.now(timezone.utc)).timestamp()
        cutoff = now_epoch - max_window_seconds
        pruned_count = 0

        with self._lock:
            # Prune card timelines
            for card_token, timeline in list(self._card_timelines.items()):
                idx_cutoff = bisect.bisect_left(timeline, (cutoff, -math.inf, ""))
                if idx_cutoff > 0:
                    pruned_count += idx_cutoff
                    self._card_timelines[card_token] = timeline[idx_cutoff:]
                if not self._card_timelines[card_token]:
                    del self._card_timelines[card_token]

            # Prune merchant timelines
            for merch_id, timeline in list(self._merchant_timelines.items()):
                idx_cutoff = bisect.bisect_left(timeline, (cutoff, "", ""))
                if idx_cutoff > 0:
                    pruned_count += idx_cutoff
                    self._merchant_timelines[merch_id] = timeline[idx_cutoff:]
                if not self._merchant_timelines[merch_id]:
                    del self._merchant_timelines[merch_id]

            # Prune idempotency seen transactions
            for tx_id, epoch in list(self._seen_tx_ids.items()):
                if epoch < cutoff:
                    del self._seen_tx_ids[tx_id]
                    pruned_count += 1

        return pruned_count

    def clear(self) -> None:
        with self._lock:
            self._card_timelines.clear()
            self._merchant_timelines.clear()
            self._seen_tx_ids.clear()
            self._last_locations.clear()
