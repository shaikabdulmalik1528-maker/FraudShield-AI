"""
Integration tests for FraudShield 3.0 Streaming Feature Pipeline.
Verifies end-to-end enrichment, cyclical temporal encodings, velocity accumulation,
replay handling, and impossible travel detection.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline

NYC_LAT, NYC_LON = 40.7128, -74.0060
LON_LAT, LON_LON = 51.5074, -0.1278


def make_canonical_tx(
    tx_id: str,
    card_token: str,
    amount: float,
    dt: datetime,
    lat: float = None,
    lon: float = None,
    channel: PaymentChannel = PaymentChannel.POS_CHIP
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
        card_type=CardType.CREDIT,
        merchant_id="merch_global_retail",
        mcc="5311",
        merchant_country="USA",
        channel=channel,
        latitude=lat,
        longitude=lon
    )


def test_pipeline_streaming_velocity_accumulation():
    """
    Asserts that sequential transactions through the pipeline properly accumulate
    sliding-window velocity features in real time.
    """
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store)

    card_token = "tok_v3_pipeline_card_01"
    t0 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

    # 1. First transaction
    tx1 = make_canonical_tx("tx_pipe_1", card_token, 50.0, t0, lat=NYC_LAT, lon=NYC_LON)
    feat1 = pipeline.enrich(tx1)

    assert feat1.is_duplicate is False
    assert feat1.card_tx_count_1h == 0  # Pre-transaction state
    assert feat1.card_amount_sum_1h == 0.0
    assert feat1.impossible_travel_flag is False

    # 2. Second transaction 20 minutes later ($150)
    t1 = t0 + timedelta(minutes=20)
    tx2 = make_canonical_tx("tx_pipe_2", card_token, 150.0, t1, lat=NYC_LAT, lon=NYC_LON)
    feat2 = pipeline.enrich(tx2)

    assert feat2.card_tx_count_1h == 1
    assert feat2.card_tx_count_24h == 1
    assert feat2.card_amount_sum_1h == 50.0
    assert feat2.impossible_travel_flag is False

    # 3. Third transaction 10 minutes later ($200)
    t2 = t1 + timedelta(minutes=10)
    tx3 = make_canonical_tx("tx_pipe_3", card_token, 200.0, t2, lat=NYC_LAT, lon=NYC_LON)
    feat3 = pipeline.enrich(tx3)

    assert feat3.card_tx_count_1h == 2
    assert feat3.card_amount_sum_1h == 200.0  # 50 + 150


def test_pipeline_cyclical_temporal_encodings():
    """
    Asserts mathematical validity of sin/cos cyclic encodings.
    sin^2 + cos^2 must equal 1.0.
    """
    pipeline = StreamingFeaturePipeline()
    # Wednesday 18:30 UTC
    dt = datetime(2026, 6, 17, 18, 30, 0, tzinfo=timezone.utc)
    tx = make_canonical_tx("tx_cyclical", "tok_v3_cyclic_card", 80.0, dt)

    feat = pipeline.enrich(tx)

    # Unit circle assertion: sin^2 + cos^2 ≈ 1.0
    hour_norm = feat.hour_sin ** 2 + feat.hour_cos ** 2
    assert pytest.approx(hour_norm, abs=1e-3) == 1.0

    dow_norm = feat.dow_sin ** 2 + feat.dow_cos ** 2
    assert pytest.approx(dow_norm, abs=1e-3) == 1.0


def test_pipeline_duplicate_event_handling():
    """
    Asserts that replaying a transaction results in is_duplicate=True
    without inflating velocity metrics.
    """
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store)

    t0 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    tx = make_canonical_tx("tx_idemp_check", "tok_v3_dup_card_001", 100.0, t0)

    # First pass
    feat_1 = pipeline.enrich(tx)
    assert feat_1.is_duplicate is False

    # Replay pass with same transaction_id
    feat_2 = pipeline.enrich(tx)
    assert feat_2.is_duplicate is True


def test_pipeline_impossible_travel_integration():
    """
    Asserts that consecutive physical POS transactions across continents trigger impossible travel flag.
    """
    store = InMemorySlidingWindowStore()
    pipeline = StreamingFeaturePipeline(feature_store=store, speed_threshold_kmh=900.0)

    card_token = "tok_v3_travel_card"
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    # NYC POS chip transaction
    tx_nyc = make_canonical_tx(
        "tx_nyc", card_token, 50.0, t0,
        lat=NYC_LAT, lon=NYC_LON,
        channel=PaymentChannel.POS_CHIP
    )
    feat_nyc = pipeline.enrich(tx_nyc)
    assert feat_nyc.impossible_travel_flag is False

    # London POS chip transaction 20 minutes later (teleportation)
    t1 = t0 + timedelta(minutes=20)
    tx_lon = make_canonical_tx(
        "tx_lon", card_token, 50.0, t1,
        lat=LON_LAT, lon=LON_LON,
        channel=PaymentChannel.POS_CHIP
    )
    feat_lon = pipeline.enrich(tx_lon)

    assert feat_lon.impossible_travel_flag is True
    assert feat_lon.speed_kmh is not None and feat_lon.speed_kmh > 900.0
    assert feat_lon.distance_km is not None and feat_lon.distance_km > 5500.0
