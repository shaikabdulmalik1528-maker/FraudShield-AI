"""
FraudShield 3.0 Streaming Feature Pipeline.
Transforms raw CanonicalTransaction models into fully enriched, feature-engineered vectors
for model scoring and offline dataset generation.
"""

import math
import time
import logging
from typing import Optional, List
from backend.app.v3.schemas.canonical import CanonicalTransaction
from backend.app.v3.feature_store.base import BaseFeatureStore
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.geo import (
    evaluate_impossible_travel,
    DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH
)
from backend.app.v3.feature_store.schemas import EnrichedFeatureVector, CardVelocityStats, MerchantVelocityStats

logger = logging.getLogger(__name__)


class StreamingFeaturePipeline:
    """
    Streaming feature enrichment pipeline.
    Coordinates pre-transaction sliding-window velocity retrieval,
    geo-spatial impossible travel detection, cyclical temporal encoding,
    atomic deduplication, currency normalization, and state persistence.
    """

    def __init__(
        self,
        feature_store: Optional[BaseFeatureStore] = None,
        fallback_store: Optional[BaseFeatureStore] = None,
        speed_threshold_kmh: float = DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH
    ):
        self.store = feature_store or InMemorySlidingWindowStore()
        self.fallback_store = fallback_store or InMemorySlidingWindowStore()
        self.speed_threshold_kmh = speed_threshold_kmh

    def _execute_with_resilience(self, operation_name: str, fn, fallback_fn, tracker: Optional[List[str]] = None):
        """Executes store operation with graceful failover (RESIL-01) and degraded tracking."""
        try:
            if self.store is self.fallback_store:
                if tracker is not None:
                    tracker.append(operation_name)
            return fn()
        except Exception as exc:
            logger.error(
                "StreamingFeaturePipeline: Store failure during '%s' (%s). Failing over to in-memory fallback.",
                operation_name, exc
            )
            if tracker is not None:
                tracker.append(operation_name)
            return fallback_fn()

    def enrich(self, tx: CanonicalTransaction) -> EnrichedFeatureVector:
        """
        Enriches a CanonicalTransaction into an EnrichedFeatureVector.

        Guarantees:
        - Velocity metrics capture state strictly prior to the current transaction.
        - Out-of-order events update timeline while preserving chronological window integrity.
        - Duplicates are detected and flagged without double-counting velocity.
        - Concurrent submissions are handled atomically (RACE-01).
        - Bypasses impossible travel for e-commerce transactions.
        - Flags feature degradation when primary distributed store is unavailable.
        """
        start_time = time.perf_counter()
        degraded_ops: List[str] = []

        # Step 1: Idempotency check with merchant scoping (IDEMP-02)
        is_dup = self._execute_with_resilience(
            "is_duplicate_transaction",
            lambda: self.store.is_duplicate_transaction(tx.transaction_id, merchant_id=tx.merchant_id),
            lambda: self.fallback_store.is_duplicate_transaction(tx.transaction_id, merchant_id=tx.merchant_id),
            tracker=degraded_ops
        )

        is_degraded_state = bool(degraded_ops) or (self.store is self.fallback_store)
        imputed_list = ["card_velocity", "merchant_velocity"] if is_degraded_state else []

        if is_dup:
            hour = tx.timestamp.hour + (tx.timestamp.minute / 60.0)
            dow = tx.timestamp.weekday()
            hour_sin = round(math.sin(2.0 * math.pi * hour / 24.0), 4)
            hour_cos = round(math.cos(2.0 * math.pi * hour / 24.0), 4)
            dow_sin = round(math.sin(2.0 * math.pi * dow / 7.0), 4)
            dow_cos = round(math.cos(2.0 * math.pi * dow / 7.0), 4)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 3)

            return EnrichedFeatureVector(
                transaction_id=tx.transaction_id,
                timestamp=tx.timestamp,
                amount=tx.amount,
                currency=tx.currency,
                card_pan_token=tx.card_pan_token,
                card_bin=tx.card_bin,
                card_last4=tx.card_last4,
                card_network=tx.card_network.value,
                card_type=tx.card_type.value,
                merchant_id=tx.merchant_id,
                mcc=tx.mcc,
                merchant_country=tx.merchant_country,
                channel=tx.channel.value,
                hour_sin=hour_sin,
                hour_cos=hour_cos,
                dow_sin=dow_sin,
                dow_cos=dow_cos,
                is_duplicate=True,
                is_degraded=is_degraded_state,
                features_imputed=imputed_list,
                pipeline_latency_ms=elapsed_ms
            )

        # Step 2: Retrieve pre-transaction card velocity & baseline spend (CURR-01)
        card_stats: CardVelocityStats = self._execute_with_resilience(
            "get_card_velocity_stats",
            lambda: self.store.get_card_velocity_stats(
                card_token=tx.card_pan_token,
                reference_time=tx.timestamp,
                current_amount=tx.amount,
                currency=tx.currency
            ),
            lambda: self.fallback_store.get_card_velocity_stats(
                card_token=tx.card_pan_token,
                reference_time=tx.timestamp,
                current_amount=tx.amount,
                currency=tx.currency
            ),
            tracker=degraded_ops
        )

        # Step 3: Retrieve pre-transaction merchant velocity & card diversity
        merchant_stats: MerchantVelocityStats = self._execute_with_resilience(
            "get_merchant_velocity_stats",
            lambda: self.store.get_merchant_velocity_stats(
                merchant_id=tx.merchant_id,
                reference_time=tx.timestamp
            ),
            lambda: self.fallback_store.get_merchant_velocity_stats(
                merchant_id=tx.merchant_id,
                reference_time=tx.timestamp
            ),
            tracker=degraded_ops
        )

        # Step 4: Geo-spatial impossible travel check
        last_loc = self._execute_with_resilience(
            "get_last_known_location",
            lambda: self.store.get_last_known_location(tx.card_pan_token),
            lambda: self.fallback_store.get_last_known_location(tx.card_pan_token),
            tracker=degraded_ops
        )
        impossible_flag, dist_km, delta_sec, speed_kmh = evaluate_impossible_travel(
            curr_lat=tx.latitude,
            curr_lon=tx.longitude,
            curr_time=tx.timestamp,
            last_location=last_loc,
            channel=tx.channel,
            threshold_kmh=self.speed_threshold_kmh
        )

        # Step 5: Cyclical temporal encodings
        hour_val = tx.timestamp.hour + (tx.timestamp.minute / 60.0)
        dow_val = tx.timestamp.weekday()
        hour_sin = round(math.sin(2.0 * math.pi * hour_val / 24.0), 4)
        hour_cos = round(math.cos(2.0 * math.pi * hour_val / 24.0), 4)
        dow_sin = round(math.sin(2.0 * math.pi * dow_val / 7.0), 4)
        dow_cos = round(math.cos(2.0 * math.pi * dow_val / 7.0), 4)

        # Step 6: Atomic persistence into feature store (RACE-01)
        record_success = self._execute_with_resilience(
            "record_transaction",
            lambda: self.store.record_transaction(tx),
            lambda: self.fallback_store.record_transaction(tx),
            tracker=degraded_ops
        )
        # If record_transaction returned False, a concurrent transaction won the race!
        is_duplicate_outcome = (not record_success)

        is_degraded_state = bool(degraded_ops) or (self.store is self.fallback_store)
        imputed_list = ["card_velocity", "merchant_velocity"] if is_degraded_state else []

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 3)

        return EnrichedFeatureVector(
            transaction_id=tx.transaction_id,
            timestamp=tx.timestamp,
            amount=tx.amount,
            currency=tx.currency,
            card_pan_token=tx.card_pan_token,
            card_bin=tx.card_bin,
            card_last4=tx.card_last4,
            card_network=tx.card_network.value,
            card_type=tx.card_type.value,
            merchant_id=tx.merchant_id,
            mcc=tx.mcc,
            merchant_country=tx.merchant_country,
            channel=tx.channel.value,
            # Card Velocity
            card_tx_count_1h=card_stats.tx_count_1h,
            card_tx_count_24h=card_stats.tx_count_24h,
            card_tx_count_7d=card_stats.tx_count_7d,
            card_amount_sum_1h=card_stats.amount_sum_1h,
            card_amount_sum_24h=card_stats.amount_sum_24h,
            card_amount_sum_7d=card_stats.amount_sum_7d,
            card_amount_ratio_30d=card_stats.amount_ratio_30d,
            card_amount_zscore_30d=card_stats.amount_zscore_30d,
            # Merchant Velocity
            merchant_tx_count_1h=merchant_stats.tx_count_1h,
            merchant_tx_count_24h=merchant_stats.tx_count_24h,
            merchant_distinct_cards_1h=merchant_stats.distinct_cards_1h,
            # Geo Velocity
            prev_latitude=last_loc.latitude if last_loc else None,
            prev_longitude=last_loc.longitude if last_loc else None,
            distance_km=dist_km,
            time_delta_seconds=delta_sec,
            speed_kmh=speed_kmh,
            impossible_travel_flag=impossible_flag,
            # Cyclical Temporal Encodings
            hour_sin=hour_sin,
            hour_cos=hour_cos,
            dow_sin=dow_sin,
            dow_cos=dow_cos,
            # Diagnostics
            is_duplicate=is_duplicate_outcome,
            is_degraded=is_degraded_state,
            features_imputed=imputed_list,
            pipeline_latency_ms=elapsed_ms
        )
