"""
FraudShield 3.0 Geo-Spatial Velocity & Impossible Travel Detection.
Implements the Great-Circle Haversine formula and velocity threshold evaluation (> 900 km/h).
"""

import math
from datetime import datetime
from typing import Optional, Tuple
from backend.app.v3.schemas.canonical import PaymentChannel
from backend.app.v3.feature_store.schemas import GeoLocation

# Earth radius in kilometers (WGS-84 spherical approximation)
EARTH_RADIUS_KM = 6371.0

# Commercial jet cruising speed threshold in km/h
DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH = 900.0


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes the great-circle distance between two points on a sphere
    given their longitudes and latitudes in decimal degrees.
    Returns distance in kilometers.
    """
    # Identical coordinates
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    # Clip to [0.0, 1.0] to handle floating-point precision bounds
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(EARTH_RADIUS_KM * c, 2)


def calculate_speed_kmh(distance_km: float, time_delta_seconds: float) -> float:
    """
    Calculates velocity in kilometers per hour between two consecutive events.
    """
    if time_delta_seconds <= 0:
        # If events occurred concurrently at different locations (>50 meters apart)
        return 999999.0 if distance_km > 0.05 else 0.0

    hours = time_delta_seconds / 3600.0
    return round(distance_km / hours, 2)


def evaluate_impossible_travel(
    curr_lat: Optional[float],
    curr_lon: Optional[float],
    curr_time: datetime,
    last_location: Optional[GeoLocation],
    channel: PaymentChannel,
    threshold_kmh: float = DEFAULT_IMPOSSIBLE_TRAVEL_THRESHOLD_KMH
) -> Tuple[bool, Optional[float], Optional[float], Optional[float]]:
    """
    Evaluates physical impossible travel velocity.

    Guarantees:
    - Card-Not-Present (e-commerce / MOTO) transactions bypass physical travel alerts.
    - Requires both current and prior terminal coordinates with timestamps.
    - Flags impossible travel if physical speed exceeds threshold_kmh.

    Returns:
        (impossible_travel_flag, distance_km, time_delta_seconds, speed_kmh)
    """
    # Bypass for non-physical card-not-present channels
    if channel in (PaymentChannel.ECOMMERCE, PaymentChannel.MOTO):
        return False, None, None, None

    # Missing terminal coordinates
    if curr_lat is None or curr_lon is None or last_location is None:
        return False, None, None, None

    distance_km = calculate_haversine_distance(
        lat1=last_location.latitude,
        lon1=last_location.longitude,
        lat2=curr_lat,
        lon2=curr_lon
    )

    # Time elapsed between physical events
    delta_seconds = (curr_time - last_location.timestamp).total_seconds()
    if delta_seconds < 0:
        # Out of order historical event; do not trigger impossible travel against future event
        return False, distance_km, delta_seconds, 0.0

    speed_kmh = calculate_speed_kmh(distance_km, delta_seconds)
    impossible_travel_flag = bool(speed_kmh > threshold_kmh)

    return impossible_travel_flag, distance_km, delta_seconds, speed_kmh
