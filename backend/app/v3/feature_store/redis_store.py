"""
FraudShield 3.0 Production Redis-Backed Streaming Feature Store.
Implements BaseFeatureStore using Redis Sorted Sets (ZSET), atomic SETNX idempotency,
and pipelined sliding window aggregations.
"""

import math
import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Any

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

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

# 31 days TTL for automatic memory reclamation (IDEMP-01)
DEFAULT_KEY_TTL_SECONDS = 31 * 86400
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 31 * 86400

from backend.app.v3.feature_store.currency import (
    BaseCurrencyConverter,
    default_currency_converter
)

# Atomic Transaction Registration Lua Script (RACE-01, PERF-01, GEO-01)
RECORD_TRANSACTION_LUA = """
local idemp_key = KEYS[1]
local card_key = KEYS[2]
local merch_key = KEYS[3]
local loc_key = KEYS[4]

local idemp_ttl = tonumber(ARGV[1])
local key_ttl = tonumber(ARGV[2])
local epoch = tonumber(ARGV[3])
local card_member = ARGV[4]
local merch_member = ARGV[5]
local has_loc = tonumber(ARGV[6])
local lat = ARGV[7]
local lon = ARGV[8]
local ts_iso = ARGV[9]
local cutoff_31d = tonumber(ARGV[10])

-- Step 1: Atomic Idempotency Check & Reservation (RACE-01)
if redis.call('EXISTS', idemp_key) == 1 then
    return 0
end
redis.call('SET', idemp_key, '1', 'EX', idemp_ttl)

-- Step 2: Append to Card & Merchant Timelines
redis.call('ZADD', card_key, epoch, card_member)
redis.call('EXPIRE', card_key, key_ttl)

redis.call('ZADD', merch_key, epoch, merch_member)
redis.call('EXPIRE', merch_key, key_ttl)

-- Step 3: Write-Time ZSET Trimming (PERF-01)
redis.call('ZREMRANGEBYSCORE', card_key, '-inf', '(' .. cutoff_31d)
redis.call('ZREMRANGEBYSCORE', merch_key, '-inf', '(' .. cutoff_31d)

-- Step 4: Stale Terminal Location Guard (GEO-01)
if has_loc == 1 then
    local stored_epoch = redis.call('HGET', loc_key, 'epoch')
    if (not stored_epoch) or (epoch >= tonumber(stored_epoch)) then
        redis.call('HSET', loc_key, 'latitude', lat, 'longitude', lon, 'timestamp', ts_iso, 'epoch', tostring(epoch))
        redis.call('EXPIRE', loc_key, key_ttl)
    end
end

return 1
"""


class RedisSlidingWindowStore(BaseFeatureStore):
    """
    Redis-backed streaming feature store implementation.
    - Card timelines stored in ZSET (score = timestamp epoch, member = '{tx_id}:{amount_usd}')
    - Merchant timelines stored in ZSET (score = timestamp epoch, member = '{tx_id}:{card_token}')
    - Idempotency maintained via atomic Lua SETNX reservation with 31-day TTL
    - Physical terminal locations maintained in HASH with stale overwrite guard
    - Write-time ZSET trimming prevents memory growth
    - Amounts normalized to USD (CURR-01)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_client: Optional[Any] = None,
        prefix: str = "fs3",
        currency_converter: Optional[BaseCurrencyConverter] = None
    ):
        if not REDIS_AVAILABLE and redis_client is None:
            raise RuntimeError("The 'redis' package is required to instantiate RedisSlidingWindowStore.")

        self.prefix = prefix
        self.currency_converter = currency_converter or default_currency_converter
        if redis_client is not None:
            self.client = redis_client
        else:
            url = redis_url or os.environ.get("FRAUDSHIELD_REDIS_URL", "redis://localhost:6379/0")
            self.client = redis.from_url(url, decode_responses=True)

        self._lua_record = None

    def _card_key(self, card_token: str) -> str:
        return f"{self.prefix}:card:{card_token}:txs"

    def _merch_key(self, merchant_id: str) -> str:
        return f"{self.prefix}:merch:{merchant_id}:txs"

    def _idemp_key(self, transaction_id: str, merchant_id: Optional[str] = None) -> str:
        if merchant_id:
            return f"{self.prefix}:idemp:{merchant_id}:{transaction_id}"
        return f"{self.prefix}:idemp:{transaction_id}"

    def _loc_key(self, card_token: str) -> str:
        return f"{self.prefix}:card:{card_token}:last_loc"

    def is_duplicate_transaction(self, transaction_id: str, merchant_id: Optional[str] = None) -> bool:
        if merchant_id:
            scoped_k = self._idemp_key(transaction_id, merchant_id)
            if self.client.exists(scoped_k):
                return True
        return bool(self.client.exists(self._idemp_key(transaction_id)))

    def record_transaction(self, tx: CanonicalTransaction) -> bool:
        idemp_k = self._idemp_key(tx.transaction_id, tx.merchant_id)
        epoch = tx.timestamp.timestamp()
        cutoff_31d = epoch - WINDOW_30D_SECONDS
        card_k = self._card_key(tx.card_pan_token)
        merch_k = self._merch_key(tx.merchant_id)
        loc_k = self._loc_key(tx.card_pan_token)

        # Convert to USD before recording (CURR-01)
        amount_usd = self.currency_converter.convert_to_usd(float(tx.amount), tx.currency)
        card_member = f"{tx.transaction_id}:{amount_usd}"
        merch_member = f"{tx.transaction_id}:{tx.card_pan_token}"

        has_loc = 1 if (
            tx.latitude is not None
            and tx.longitude is not None
            and tx.channel not in (PaymentChannel.ECOMMERCE, PaymentChannel.MOTO)
        ) else 0

        lat_str = str(tx.latitude or 0.0)
        lon_str = str(tx.longitude or 0.0)
        ts_iso = tx.timestamp.isoformat()

        # Try Lua script first (atomic across real Redis / fakeredis)
        try:
            res = self.client.eval(
                RECORD_TRANSACTION_LUA,
                4,
                idemp_k, card_k, merch_k, loc_k,
                DEFAULT_IDEMPOTENCY_TTL_SECONDS,
                DEFAULT_KEY_TTL_SECONDS,
                epoch,
                card_member,
                merch_member,
                has_loc,
                lat_str,
                lon_str,
                ts_iso,
                cutoff_31d
            )
            return bool(res == 1)
        except Exception:
            # Fallback for simple mock clients without eval support
            is_new = self.client.set(idemp_k, "1", nx=True, ex=DEFAULT_IDEMPOTENCY_TTL_SECONDS)
            if not is_new:
                return False

            pipe = self.client.pipeline()
            pipe.zadd(card_k, {card_member: epoch})
            pipe.expire(card_k, DEFAULT_KEY_TTL_SECONDS)
            pipe.zremrangebyscore(card_k, "-inf", f"({cutoff_31d}")

            pipe.zadd(merch_k, {merch_member: epoch})
            pipe.expire(merch_k, DEFAULT_KEY_TTL_SECONDS)
            pipe.zremrangebyscore(merch_k, "-inf", f"({cutoff_31d}")

            if has_loc == 1:
                loc_data = {
                    "latitude": lat_str,
                    "longitude": lon_str,
                    "timestamp": ts_iso,
                    "epoch": str(epoch)
                }
                pipe.hset(loc_k, mapping=loc_data)
                pipe.expire(loc_k, DEFAULT_KEY_TTL_SECONDS)

            pipe.execute()
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
        card_k = self._card_key(card_token)
        t_30d = ref_epoch - WINDOW_30D_SECONDS

        # Query all prior events within 30 days strictly preceding reference_time
        # Range: [t_30d, (ref_epoch
        entries = self.client.zrangebyscore(
            name=card_k,
            min=t_30d,
            max=f"({ref_epoch}",
            withscores=True
        )

        if not entries:
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

        t_1h = ref_epoch - WINDOW_1H_SECONDS
        t_24h = ref_epoch - WINDOW_24H_SECONDS
        t_7d = ref_epoch - WINDOW_7D_SECONDS

        count_1h = 0
        count_24h = 0
        count_7d = 0
        count_30d = len(entries)

        sum_1h = 0.0
        sum_24h = 0.0
        sum_7d = 0.0
        amounts_30d: List[float] = []

        for member, score in entries:
            try:
                amt = float(member.split(":")[1])
            except (IndexError, ValueError):
                amt = 0.0

            amounts_30d.append(amt)

            if score >= t_7d:
                count_7d += 1
                sum_7d += amt
                if score >= t_24h:
                    count_24h += 1
                    sum_24h += amt
                    if score >= t_1h:
                        count_1h += 1
                        sum_1h += amt

        mean_30d = round(sum(amounts_30d) / count_30d, 2)
        variance = sum((x - mean_30d) ** 2 for x in amounts_30d) / count_30d
        std_30d = round(math.sqrt(variance), 2)
        ratio_30d = round(current_amount_usd / max(mean_30d, 0.01), 3)
        zscore_30d = round((current_amount_usd - mean_30d) / std_30d, 3) if std_30d > 1e-4 else 0.0

        return CardVelocityStats(
            tx_count_1h=count_1h,
            tx_count_24h=count_24h,
            tx_count_7d=count_7d,
            tx_count_30d=count_30d,
            amount_sum_1h=round(sum_1h, 2),
            amount_sum_24h=round(sum_24h, 2),
            amount_sum_7d=round(sum_7d, 2),
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
        merch_k = self._merch_key(merchant_id)
        t_24h = ref_epoch - WINDOW_24H_SECONDS

        entries = self.client.zrangebyscore(
            name=merch_k,
            min=t_24h,
            max=f"({ref_epoch}",
            withscores=True
        )

        if not entries:
            return MerchantVelocityStats(tx_count_1h=0, tx_count_24h=0, distinct_cards_1h=0)

        t_1h = ref_epoch - WINDOW_1H_SECONDS
        count_1h = 0
        count_24h = len(entries)
        cards_1h = set()

        for member, score in entries:
            parts = member.split(":", 1)
            card_token = parts[1] if len(parts) > 1 else ""
            if score >= t_1h:
                count_1h += 1
                if card_token:
                    cards_1h.add(card_token)

        return MerchantVelocityStats(
            tx_count_1h=count_1h,
            tx_count_24h=count_24h,
            distinct_cards_1h=len(cards_1h)
        )

    def get_last_known_location(self, card_token: str) -> Optional[GeoLocation]:
        loc_k = self._loc_key(card_token)
        data = self.client.hgetall(loc_k)
        if not data or "latitude" not in data or "longitude" not in data:
            return None

        try:
            return GeoLocation(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
                timestamp=datetime.fromisoformat(data["timestamp"])
            )
        except (ValueError, KeyError):
            return None

    def prune_expired(
        self,
        reference_time: Optional[datetime] = None,
        max_window_seconds: int = WINDOW_30D_SECONDS
    ) -> int:
        now_epoch = (reference_time or datetime.now(timezone.utc)).timestamp()
        cutoff = now_epoch - max_window_seconds

        pruned = 0
        # Scan and prune keys
        for key in self.client.scan_iter(f"{self.prefix}:*:txs"):
            removed = self.client.zremrangebyscore(key, "-inf", f"({cutoff}")
            pruned += removed

        return pruned

    def clear(self) -> None:
        keys = list(self.client.scan_iter(f"{self.prefix}:*"))
        if keys:
            self.client.delete(*keys)
