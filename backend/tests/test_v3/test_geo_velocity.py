"""
Unit tests for FraudShield 3.0 Geo-Spatial Velocity & Impossible Travel Detection.
Verifies Haversine great-circle distance, velocity calculation, e-commerce bypass, and >900 km/h thresholding.
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.app.v3.schemas.canonical import PaymentChannel
from backend.app.v3.feature_store.schemas import GeoLocation
from backend.app.v3.feature_store.geo import (
    calculate_haversine_distance,
    calculate_speed_kmh,
    evaluate_impossible_travel
)

# Known coordinates
NYC_LAT, NYC_LON = 40.7128, -74.0060
LON_LAT, LON_LON = 51.5074, -0.1278
PHL_LAT, PHL_LON = 39.9526, -75.1652


def test_haversine_distance_accuracy():
    """Asserts that great-circle distance matches geographic truth."""
    # NYC to London is approximately 5570 km
    dist_nyc_lon = calculate_haversine_distance(NYC_LAT, NYC_LON, LON_LAT, LON_LON)
    assert 5560.0 <= dist_nyc_lon <= 5585.0

    # NYC to Philadelphia is approximately 130 km
    dist_nyc_phl = calculate_haversine_distance(NYC_LAT, NYC_LON, PHL_LAT, PHL_LON)
    assert 120.0 <= dist_nyc_phl <= 140.0

    # Identical coordinates
    dist_zero = calculate_haversine_distance(NYC_LAT, NYC_LON, NYC_LAT, NYC_LON)
    assert dist_zero == 0.0


def test_speed_calculation():
    """Asserts speed calculation in km/h."""
    # 500 km in 2 hours = 250 km/h
    speed = calculate_speed_kmh(500.0, 7200.0)
    assert speed == 250.0

    # 100 km in 0 seconds = 999999.0 (infinite / teleportation)
    speed_zero_time = calculate_speed_kmh(100.0, 0.0)
    assert speed_zero_time == 999999.0


def test_impossible_travel_physical_terminal_flagged():
    """
    Asserts that physical transactions separated by impossible speeds (>900 km/h) are flagged.
    NYC -> London in 15 minutes (~22,000 km/h).
    """
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    last_loc = GeoLocation(latitude=NYC_LAT, longitude=NYC_LON, timestamp=t0)

    t1 = t0 + timedelta(minutes=15)
    flag, dist, delta_sec, speed = evaluate_impossible_travel(
        curr_lat=LON_LAT,
        curr_lon=LON_LON,
        curr_time=t1,
        last_location=last_loc,
        channel=PaymentChannel.POS_CHIP,
        threshold_kmh=900.0
    )

    assert flag is True
    assert dist is not None and dist > 5500.0
    assert speed is not None and speed > 900.0
    assert delta_sec == 900.0


def test_realistic_travel_cleared():
    """
    Asserts that realistic ground travel is NOT flagged.
    NYC -> Philadelphia in 2.5 hours (~52 km/h).
    """
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    last_loc = GeoLocation(latitude=NYC_LAT, longitude=NYC_LON, timestamp=t0)

    t1 = t0 + timedelta(hours=2, minutes=30)
    flag, dist, delta_sec, speed = evaluate_impossible_travel(
        curr_lat=PHL_LAT,
        curr_lon=PHL_LON,
        curr_time=t1,
        last_location=last_loc,
        channel=PaymentChannel.POS_CONTACTLESS,
        threshold_kmh=900.0
    )

    assert flag is False
    assert speed is not None and speed < 100.0


def test_ecommerce_bypasses_impossible_travel():
    """
    Asserts that Card-Not-Present (e-commerce) transactions bypass impossible travel detection.
    """
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    last_loc = GeoLocation(latitude=NYC_LAT, longitude=NYC_LON, timestamp=t0)

    t1 = t0 + timedelta(minutes=5)
    flag, dist, delta_sec, speed = evaluate_impossible_travel(
        curr_lat=LON_LAT,
        curr_lon=LON_LON,
        curr_time=t1,
        last_location=last_loc,
        channel=PaymentChannel.ECOMMERCE
    )

    assert flag is False
    assert dist is None
    assert speed is None


def test_missing_coordinates_handled_gracefully():
    """Asserts that transactions with missing coordinates return False without crashing."""
    t0 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    flag, dist, delta_sec, speed = evaluate_impossible_travel(
        curr_lat=None,
        curr_lon=None,
        curr_time=t0,
        last_location=None,
        channel=PaymentChannel.POS_CHIP
    )

    assert flag is False
    assert dist is None
