"""
FraudShield 3.0 ISO 8583 Message Schemas.
Definitions for Message Type Identifiers (MTIs), Bitmaps, and Data Elements (DEs).
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_serializer


class Iso8583Mti(str, Enum):
    """Standard ISO 8583 Message Type Identifiers."""
    AUTH_REQUEST = "0100"
    AUTH_RESPONSE = "0110"
    FINANCIAL_REQUEST = "0200"
    FINANCIAL_RESPONSE = "0210"
    REVERSAL_ADVICE = "0420"
    REVERSAL_RESPONSE = "0430"
    NETWORK_MANAGEMENT = "0800"


class Iso8583ParsedPayload(BaseModel):
    """Encapsulates parsed elements from an ISO 8583 message."""
    model_config = ConfigDict(extra="ignore")

    mti: Iso8583Mti = Field(..., description="4-digit Message Type Identifier")
    pan: Optional[str] = Field(None, description="DE 2: Primary Account Number (transient in-memory only)")
    processing_code: str = Field(default="000000", description="DE 3: Processing Code")
    amount_cents: int = Field(..., ge=0, description="DE 4: Amount in minor currency units (cents)")
    transmission_datetime: str = Field(..., description="DE 7: Transmission Date & Time (MMDDhhmmss)")
    stan: str = Field(..., description="DE 11: Systems Trace Audit Number (6 digits)")
    expiration_date: Optional[str] = Field(None, description="DE 14: Expiration Date (YYMM)")
    mcc: str = Field(..., description="DE 18: Merchant Category Code (4 digits)")
    acquirer_country: str = Field(default="840", description="DE 19: Acquirer Country Code (ISO numeric)")
    pos_entry_mode: str = Field(default="051", description="DE 22: Point of Service Entry Mode")
    pos_condition_code: str = Field(default="00", description="DE 25: Point of Service Condition Code")
    acquirer_id: Optional[str] = Field(None, description="DE 32: Acquiring Institution ID")
    rrn: Optional[str] = Field(None, description="DE 37: Retrieval Reference Number (12 characters)")
    terminal_id: str = Field(..., description="DE 41: Card Acceptor Terminal ID")
    merchant_id: str = Field(..., description="DE 42: Card Acceptor Identification Code")
    card_acceptor_name_loc: Optional[str] = Field(None, description="DE 43: Card Acceptor Name/Location")
    currency_code: str = Field(default="840", description="DE 49: Currency Code (ISO 4217 numeric)")

    @field_serializer("pan")
    def mask_pan_on_serialization(self, pan: Optional[str]) -> Optional[str]:
        """Automatically masks PAN when serialized to JSON or dict to prevent log leakage."""
        if not pan:
            return None
        clean = "".join(filter(str.isdigit, str(pan)))
        if len(clean) < 10:
            return "XXXXXXXXXXXX"
        first6 = clean[:6]
        last4 = clean[-4:]
        masked_count = len(clean) - 10
        return f"{first6}{'X' * masked_count}{last4}"


class Iso8583Message(BaseModel):
    """Raw representation of parsed ISO 8583 frame."""
    mti: str
    primary_bitmap_hex: str
    secondary_bitmap_hex: Optional[str] = None
    data_elements: Dict[int, str] = Field(default_factory=dict)
    raw_payload: str
