"""
Unit tests for RedisSlidingWindowStore using a mock Redis client.
Verifies keyspace conventions, pipeline orchestration, atomic SETNX idempotency, and ZSET aggregations.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.redis_store import RedisSlidingWindowStore


class MockRedisPipeline:
    def __init__(self, client: "MockRedisClient"):
        self.client = client
        self.commands: List[Tuple[str, tuple, dict]] = []

    def zadd(self, name: str, mapping: Dict[str, float]):
        self.commands.append(("zadd", (name, mapping), {}))
        return self

    def expire(self, name: str, time: int):
        self.commands.append(("expire", (name, time), {}))
        return self

    def hset(self, name: str, mapping: Dict[str, str]):
        self.commands.append(("hset", (name, mapping), {}))
        return self

    def zremrangebyscore(self, name: str, min: Any, max: Any):
        self.commands.append(("zremrangebyscore", (name, min, max), {}))
        return self

    def execute(self):
        results = []
        for cmd, args, kwargs in self.commands:
            method = getattr(self.client, cmd)
            results.append(method(*args, **kwargs))
        self.commands.clear()
        return results


class MockRedisClient:
    """In-memory mock supporting core Redis data structures for feature store verification."""
    def __init__(self):
        self.strings: Dict[str, str] = {}
        self.zsets: Dict[str, Dict[str, float]] = {}
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.ttls: Dict[str, int] = {}

    def set(self, name: str, value: str, nx: bool = False, ex: int = None) -> bool:
        if nx and name in self.strings:
            return False
        self.strings[name] = value
        if ex:
            self.ttls[name] = ex
        return True

    def exists(self, *names: str) -> int:
        return sum(1 for n in names if n in self.strings or n in self.zsets or n in self.hashes)

    def zadd(self, name: str, mapping: Dict[str, float]) -> int:
        if name not in self.zsets:
            self.zsets[name] = {}
        added = 0
        for member, score in mapping.items():
            if member not in self.zsets[name]:
                added += 1
            self.zsets[name][member] = float(score)
        return added

    def zrangebyscore(
        self,
        name: str,
        min: Any,
        max: Any,
        withscores: bool = False
    ) -> List[Any]:
        if name not in self.zsets:
            return []

        min_val = -float("inf") if str(min) == "-inf" else float(min)
        max_str = str(max)
        exclusive_max = max_str.startswith("(")
        max_val = float(max_str[1:]) if exclusive_max else float(max_str)

        items = []
        for member, score in self.zsets[name].items():
            if exclusive_max:
                if min_val <= score < max_val:
                    items.append((member, score))
            else:
                if min_val <= score <= max_val:
                    items.append((member, score))

        # Sort by score ascending
        items.sort(key=lambda x: x[1])

        if withscores:
            return items
        return [m for m, _ in items]

    def zremrangebyscore(self, name: str, min: Any, max: Any) -> int:
        if name not in self.zsets:
            return 0
        matching = self.zrangebyscore(name, min, max, withscores=False)
        for m in matching:
            del self.zsets[name][m]
        return len(matching)

    def hset(self, name: str, mapping: Dict[str, str]) -> int:
        if name not in self.hashes:
            self.hashes[name] = {}
        self.hashes[name].update(mapping)
        return len(mapping)

    def hgetall(self, name: str) -> Dict[str, str]:
        return dict(self.hashes.get(name, {}))

    def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    def pipeline(self) -> MockRedisPipeline:
        return MockRedisPipeline(self)

    def scan_iter(self, match: str = "*"):
        all_keys = set(self.strings.keys()) | set(self.zsets.keys()) | set(self.hashes.keys())
        prefix = match.replace("*", "")
        for k in all_keys:
            if k.startswith(prefix):
                yield k

    def delete(self, *names: str) -> int:
        count = 0
        for n in names:
            if n in self.strings:
                del self.strings[n]
                count += 1
            if n in self.zsets:
                del self.zsets[n]
                count += 1
            if n in self.hashes:
                del self.hashes[n]
                count += 1
        return count


def make_test_canonical_tx(
    tx_id: str,
    card_token: str,
    amount: float,
    dt: datetime,
    lat: float = 40.7128,
    lon: float = -74.0060
) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=tx_id,
        timestamp=dt,
        amount=amount,
        currency="USD",
        card_pan_token=card_token,
        card_bin="453201",
        card_last4="0366",
        card_network=CardNetwork.VISA,
        card_type=CardType.DEBIT,
        merchant_id="merch_redis_test",
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.POS_CHIP,
        latitude=lat,
        longitude=lon
    )


def test_redis_feature_store_end_to_end_mock():
    """
    Asserts that RedisSlidingWindowStore correctly executes against Redis data structures.
    """
    mock_client = MockRedisClient()
    store = RedisSlidingWindowStore(redis_client=mock_client, prefix="fs3_test")

    card_token = "tok_v3_redis_card"
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Record tx 1 (amount 50)
    tx1 = make_test_canonical_tx("tx_r1", card_token, 50.0, t0 - timedelta(minutes=30))
    res1 = store.record_transaction(tx1)
    assert res1 is True

    # Check that Redis keys were populated
    assert f"fs3_test:card:{card_token}:txs" in mock_client.zsets
    assert (f"fs3_test:idemp:merch_redis_test:tx_r1" in mock_client.strings or f"fs3_test:idemp:tx_r1" in mock_client.strings)
    assert f"fs3_test:card:{card_token}:last_loc" in mock_client.hashes

    # 2. Duplicate submission fails
    res_dup = store.record_transaction(tx1)
    assert res_dup is False

    # 3. Record tx 2 (amount 100) 10 minutes ago
    tx2 = make_test_canonical_tx("tx_r2", card_token, 100.0, t0 - timedelta(minutes=10))
    res2 = store.record_transaction(tx2)
    assert res2 is True

    # 4. Query velocity statistics at t0
    stats = store.get_card_velocity_stats(card_token, reference_time=t0, current_amount=75.0)

    assert stats.tx_count_1h == 2
    assert stats.tx_count_24h == 2
    assert stats.amount_sum_1h == 150.0  # 50 + 100
    assert stats.amount_mean_30d == 75.0  # (50 + 100) / 2
    assert stats.amount_ratio_30d == 1.0  # 75 / 75

    # 5. Query last known location
    loc = store.get_last_known_location(card_token)
    assert loc is not None
    assert loc.latitude == 40.7128
    assert loc.longitude == -74.0060

    # 6. Merchant stats
    m_stats = store.get_merchant_velocity_stats("merch_redis_test", reference_time=t0)
    assert m_stats.tx_count_1h == 2
    assert m_stats.distinct_cards_1h == 1
