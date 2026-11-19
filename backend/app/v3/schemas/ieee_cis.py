"""
FraudShield 3.0 IEEE-CIS Schema Definitions.
Typed structure for the IEEE-CIS / Vesta Payment Fraud Detection tabular dataset.
Note: IEEE-CIS is tabular e-commerce payment transaction data, NOT native ISO 8583 data.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class IeeeCisRecord(BaseModel):
    """
    Representation of an IEEE-CIS (Vesta) tabular transaction row.
    Combines transaction attributes with engineered velocity and identity features.
    """
    model_config = ConfigDict(extra="allow")

    # Core Transaction Fields
    TransactionID: int = Field(..., description="Unique transaction integer ID")
    TransactionDT: int = Field(..., ge=0, description="Timestep in seconds from reference epoch")
    TransactionAmt: float = Field(..., gt=0.0, description="Transaction payment amount in USD")
    ProductCD: str = Field(default="W", description="Product code (W, C, R, H, S)")

    # Card Fields
    card1: int = Field(..., description="Issuer bank identification number (card BIN proxy)")
    card2: Optional[float] = Field(None, description="Card bank code")
    card3: Optional[float] = Field(None, description="Card country code")
    card4: Optional[str] = Field(None, description="Card network (visa, mastercard, amex, discover)")
    card5: Optional[float] = Field(None, description="Card sub-category")
    card6: Optional[str] = Field(None, description="Card type (debit, credit, charge card)")

    # Address & Distance
    addr1: Optional[float] = Field(None, description="Billing zip/region code")
    addr2: Optional[float] = Field(None, description="Billing country code")
    dist1: Optional[float] = Field(None, description="Distance proxy 1")
    dist2: Optional[float] = Field(None, description="Distance proxy 2")

    # Email Domains
    P_emaildomain: Optional[str] = Field(None, description="Purchaser email domain")
    R_emaildomain: Optional[str] = Field(None, description="Recipient email domain")

    # Device & Identity (Optional / Joined)
    DeviceType: Optional[str] = Field(None, description="mobile or desktop")
    DeviceInfo: Optional[str] = Field(None, description="Hardware/browser description")

    # Ground truth (if available in historical/training records)
    isFraud: Optional[int] = Field(None, ge=0, le=1, description="Ground truth fraud label (0=legit, 1=fraud)")
