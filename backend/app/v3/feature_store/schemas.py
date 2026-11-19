"""
FraudShield 3.0 Streaming Feature Store Data Schemas.
Defines models for velocity aggregations, geo-spatial location, and enriched feature vectors.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class GeoLocation(BaseModel):
    """Geographic terminal or event coordinate with timestamp."""
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    timestamp: datetime = Field(..., description="Timestamp of physical terminal observation")


class CardVelocityStats(BaseModel):
    """Sliding-window velocity metrics aggregated at cardholder/account token level."""
    model_config = ConfigDict(frozen=True)

    tx_count_1h: int = Field(default=0, ge=0, description="Number of card transactions in past 1 hour")
    tx_count_24h: int = Field(default=0, ge=0, description="Number of card transactions in past 24 hours")
    tx_count_7d: int = Field(default=0, ge=0, description="Number of card transactions in past 7 days")
    tx_count_30d: int = Field(default=0, ge=0, description="Number of card transactions in past 30 days")

    amount_sum_1h: float = Field(default=0.0, ge=0.0, description="Cumulative spend in past 1 hour")
    amount_sum_24h: float = Field(default=0.0, ge=0.0, description="Cumulative spend in past 24 hours")
    amount_sum_7d: float = Field(default=0.0, ge=0.0, description="Cumulative spend in past 7 days")

    amount_mean_30d: float = Field(default=0.0, ge=0.0, description="Mean transaction spend over past 30 days")
    amount_std_30d: float = Field(default=0.0, ge=0.0, description="Standard deviation of spend over past 30 days")

    amount_ratio_30d: float = Field(default=1.0, ge=0.0, description="Ratio of current amount to 30d mean spend")
    amount_zscore_30d: float = Field(default=0.0, description="Z-score deviation from 30d mean spend")


class MerchantVelocityStats(BaseModel):
    """Sliding-window velocity metrics aggregated at merchant identifier level."""
    model_config = ConfigDict(frozen=True)

    tx_count_1h: int = Field(default=0, ge=0, description="Total transactions processed at merchant in past 1 hour")
    tx_count_24h: int = Field(default=0, ge=0, description="Total transactions processed at merchant in past 24 hours")
    distinct_cards_1h: int = Field(default=0, ge=0, description="Count of distinct card tokens seen in past 1 hour")


class EnrichedFeatureVector(BaseModel):
    """
    Standardized streaming feature vector ready for downstream model inference and risk scoring.
    Synthesizes transaction attributes, streaming sliding-window velocity, geo-velocity, and temporal encodings.
    """
    model_config = ConfigDict(frozen=True)

    # Core Transaction Context
    transaction_id: str = Field(..., description="Unique transaction idempotency key")
    timestamp: datetime = Field(..., description="UTC authorization timestamp")
    amount: float = Field(..., ge=0.0, description="Authorized transaction amount in major currency units")
    currency: str = Field(..., description="ISO 4217 3-letter currency code")
    card_pan_token: str = Field(..., description="Salted HMAC token representing cardholder account")
    card_bin: str = Field(..., description="First 6 digits identifying issuing bank")
    card_last4: str = Field(..., description="Last 4 digits of card")
    card_network: str = Field(..., description="Card network (VISA, MASTERCARD, etc.)")
    card_type: str = Field(..., description="Card funding type (DEBIT, CREDIT, etc.)")
    merchant_id: str = Field(..., description="Merchant identifier / card acceptor code")
    mcc: str = Field(..., description="Merchant Category Code")
    merchant_country: str = Field(..., description="Merchant country code")
    channel: str = Field(..., description="Payment acceptance channel")

    # Card Velocity Features (Pre-Transaction Window)
    card_tx_count_1h: int = Field(default=0, ge=0)
    card_tx_count_24h: int = Field(default=0, ge=0)
    card_tx_count_7d: int = Field(default=0, ge=0)
    card_amount_sum_1h: float = Field(default=0.0, ge=0.0)
    card_amount_sum_24h: float = Field(default=0.0, ge=0.0)
    card_amount_sum_7d: float = Field(default=0.0, ge=0.0)
    card_amount_ratio_30d: float = Field(default=1.0, ge=0.0)
    card_amount_zscore_30d: float = Field(default=0.0)

    # Merchant Velocity Features (Pre-Transaction Window)
    merchant_tx_count_1h: int = Field(default=0, ge=0)
    merchant_tx_count_24h: int = Field(default=0, ge=0)
    merchant_distinct_cards_1h: int = Field(default=0, ge=0)

    # Geo-Spatial Travel Features
    prev_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    prev_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    distance_km: Optional[float] = Field(None, ge=0.0)
    time_delta_seconds: Optional[float] = Field(None, ge=0.0)
    speed_kmh: Optional[float] = Field(None, ge=0.0)
    impossible_travel_flag: bool = Field(default=False)

    # Cyclical Temporal Encodings
    hour_sin: float = Field(..., ge=-1.0, le=1.0)
    hour_cos: float = Field(..., ge=-1.0, le=1.0)
    dow_sin: float = Field(..., ge=-1.0, le=1.0)
    dow_cos: float = Field(..., ge=-1.0, le=1.0)

    # Pipeline Processing Metadata
    is_duplicate: bool = Field(default=False, description="Flag indicating event was already processed")
    is_degraded: bool = Field(default=False, description="Flag indicating feature store operates in degraded fallback mode")
    features_imputed: List[str] = Field(default_factory=list, description="List of behavioral features that were imputed or uncoordinated")
    pipeline_latency_ms: float = Field(default=0.0, ge=0.0, description="Feature extraction latency in milliseconds")
