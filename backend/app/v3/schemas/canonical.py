"""
FraudShield 3.0 Canonical Transaction Schema.
Normalized, vendor-neutral representation for all ingested payment transactions.
Adheres strictly to PCI-DSS standards: zero storage or transmission of raw PAN.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, ConfigDict


class CardNetwork(str, Enum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"
    DISCOVER = "DISCOVER"
    JCB = "JCB"
    DINERS = "DINERS"
    UNIONPAY = "UNIONPAY"
    OTHER = "OTHER"


class CardType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    PREPAID = "PREPAID"
    UNKNOWN = "UNKNOWN"


class PaymentChannel(str, Enum):
    POS_CHIP = "POS_CHIP"
    POS_CONTACTLESS = "POS_CONTACTLESS"
    POS_SWIPE = "POS_SWIPE"
    POS_MANUAL = "POS_MANUAL"
    ECOMMERCE = "ECOMMERCE"
    MOTO = "MOTO"  # Mail Order / Telephone Order
    ATM = "ATM"
    OTHER = "OTHER"


class ValidationResult(BaseModel):
    """Encapsulates validation outcome with detailed diagnostics."""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CanonicalTransaction(BaseModel):
    """
    Standardized internal representation of a financial transaction across all adapters.
    Guarantees structural consistency for downstream feature stores and inference models.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Core Transaction Identifiers
    transaction_id: str = Field(..., min_length=1, description="Unique transaction idempotency key")
    timestamp: datetime = Field(..., description="UTC authorization timestamp")
    amount: float = Field(..., ge=0.0, description="Authorized transaction amount in primary currency units")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 3-letter currency code")

    # Card & Account Attributes (PCI-DSS Tokenized)
    card_pan_token: str = Field(..., min_length=16, description="HMAC-SHA256 salted token of Card PAN")
    card_bin: str = Field(..., min_length=6, max_length=8, description="First 6-8 digits representing Issuer ID")
    card_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    card_network: CardNetwork = Field(default=CardNetwork.OTHER, description="Card payment network")
    card_type: CardType = Field(default=CardType.UNKNOWN, description="Card funding source")

    # Merchant & Channel Attributes
    merchant_id: str = Field(..., min_length=1, description="Merchant identifier / Acquirer account ID")
    mcc: str = Field(..., min_length=4, max_length=4, description="ISO 18245 4-digit Merchant Category Code")
    merchant_country: str = Field(default="USA", min_length=2, max_length=3, description="ISO country code")
    channel: PaymentChannel = Field(default=PaymentChannel.ECOMMERCE, description="Payment acceptance channel")
    pos_entry_mode: Optional[str] = Field(default="05", description="ISO 8583 DE 22 entry mode code")

    # Device & Network Context (E-Commerce / Card-Not-Present)
    ip_address_hash: Optional[str] = Field(None, description="Salted hash of client IP address")
    device_fingerprint: Optional[str] = Field(None, description="Hashed hardware/browser fingerprint")
    billing_shipping_match: Optional[bool] = Field(None, description="Address Verification System (AVS) match flag")
    cvv_result_code: Optional[str] = Field(None, description="CVV verification result code (M=Match, N=No Match)")

    # Geo-Spatial Coordinates (Optional for physical POS)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Terminal latitude")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Terminal longitude")

    # Metadata Bag for Adapter-Specific Attributes
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary adapter-specific metadata")

    @field_validator("timestamp")
    @classmethod
    def validate_utc_timestamp(cls, v: datetime) -> datetime:
        """Enforces UTC timezone awareness on all canonical transaction timestamps (TIME-01)."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @field_validator("mcc")
    @classmethod
    def validate_mcc(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 4:
            raise ValueError(f"MCC must be exactly 4 numeric digits, got '{v}'")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        v_upper = v.upper()
        if not v_upper.isalpha() or len(v_upper) != 3:
            raise ValueError(f"Currency must be an ISO 4217 3-letter code, got '{v}'")
        return v_upper

    @field_validator("card_bin")
    @classmethod
    def validate_card_bin(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError(f"Card BIN must contain only numeric digits, got '{v}'")
        return v

    @field_validator("card_last4")
    @classmethod
    def validate_card_last4(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError(f"Card last4 must contain only numeric digits, got '{v}'")
        return v
