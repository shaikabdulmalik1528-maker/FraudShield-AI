"""
FraudShield 3.0 IEEE-CIS Tabular Dataset Adapter.
Scaffolding adapter mapping Kaggle / Vesta tabular transactions into CanonicalTransaction models.

CRITICAL DOMAIN DISTINCTION:
IEEE-CIS is an e-commerce tabular transaction dataset with Vesta-engineered features;
it is NOT native ISO 8583 financial messaging data.
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone, timedelta

from backend.app.v3.adapters.base import BaseTransactionAdapter
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.services.token_service import KmsTokenService


# Reference start timestamp for IEEE-CIS TransactionDT (Kaggle consensus: Dec 1, 2017 UTC)
IEEE_CIS_REFERENCE_EPOCH = datetime(2017, 12, 1, 0, 0, 0, tzinfo=timezone.utc)

# ProductCD to ISO 18245 MCC Proxy Mapping
PRODUCT_MCC_MAP = {
    "W": "5311",  # Department Store / General Merchandise
    "C": "5999",  # Miscellaneous and Specialty Retail
    "R": "5812",  # Eating Places / Restaurants
    "H": "7011",  # Hotels, Motels, and Resorts
    "S": "4814"   # Telecommunication Services
}

# card4 to CardNetwork Mapping
CARD_NETWORK_MAP = {
    "visa": CardNetwork.VISA,
    "mastercard": CardNetwork.MASTERCARD,
    "american express": CardNetwork.AMEX,
    "discover": CardNetwork.DISCOVER
}

# card6 to CardType Mapping
CARD_TYPE_MAP = {
    "debit": CardType.DEBIT,
    "credit": CardType.CREDIT,
    "charge card": CardType.CREDIT,
    "debit or credit": CardType.UNKNOWN
}


class IeeeCisAdapter(BaseTransactionAdapter):
    """
    Adapter for IEEE-CIS (Vesta) tabular records.
    Normalizes Vesta raw tabular attributes into CanonicalTransaction.
    """

    def __init__(self, token_service: Optional[KmsTokenService] = None):
        self.token_service = token_service or KmsTokenService()

    def get_schema_type(self) -> str:
        return "IEEE_CIS"

    def validate(self, raw_payload: Any) -> Tuple[bool, List[str]]:
        """
        Validates the presence of core IEEE-CIS required columns.
        """
        errors = []

        if not isinstance(raw_payload, dict):
            return False, ["Payload must be a dictionary representing an IEEE-CIS transaction row"]

        # 1. TransactionID
        tx_id = raw_payload.get("TransactionID")
        if tx_id is None:
            errors.append("Missing mandatory 'TransactionID'")

        # 2. TransactionAmt
        amt = raw_payload.get("TransactionAmt")
        if amt is None:
            errors.append("Missing mandatory 'TransactionAmt'")
        else:
            try:
                amt_float = float(amt)
                if amt_float <= 0.0:
                    errors.append(f"'TransactionAmt' must be greater than zero, got {amt_float}")
            except (ValueError, TypeError):
                errors.append(f"'TransactionAmt' must be numeric, got '{amt}'")

        # 3. TransactionDT
        dt = raw_payload.get("TransactionDT")
        if dt is None:
            errors.append("Missing mandatory 'TransactionDT'")
        else:
            try:
                dt_int = int(dt)
                if dt_int < 0:
                    errors.append(f"'TransactionDT' must be non-negative, got {dt_int}")
            except (ValueError, TypeError):
                errors.append(f"'TransactionDT' must be an integer, got '{dt}'")

        # 4. card1
        card1 = raw_payload.get("card1")
        if card1 is None:
            errors.append("Missing mandatory 'card1' (Issuer Bank ID proxy)")

        return len(errors) == 0, errors

    def adapt(self, raw_payload: Any) -> CanonicalTransaction:
        """
        Transforms validated IEEE-CIS tabular record into CanonicalTransaction.
        """
        is_valid, errors = self.validate(raw_payload)
        if not is_valid:
            raise ValueError(f"IEEE-CIS payload validation failed: {'; '.join(errors)}")

        tx_id = str(raw_payload["TransactionID"])
        amount = round(float(raw_payload["TransactionAmt"]), 2)

        # Synthesize realistic UTC timestamp from TransactionDT offset
        dt_seconds = int(raw_payload["TransactionDT"])
        timestamp = IEEE_CIS_REFERENCE_EPOCH + timedelta(seconds=dt_seconds)

        # Derive card attributes from card1-card6
        card1 = str(raw_payload.get("card1", "999999")).split(".")[0]
        card2 = str(raw_payload.get("card2") or "0").split(".")[0]
        card3 = str(raw_payload.get("card3") or "0").split(".")[0]

        # In IEEE-CIS, card1 is an issuer code; format as 6-digit BIN
        card_bin = card1.zfill(6)[:6]
        card_last4 = card1.zfill(4)[-4:]

        # Billing address region for disambiguating card accounts (DATA-01)
        addr1 = str(raw_payload.get("addr1") or "0").split(".")[0]

        # Tokenize cardholder identity based on composite card + billing attributes
        card_composite = f"ieee_{card1}_{card2}_{card3}_{addr1}"
        card_pan_token = self.token_service.tokenize_pan(card_composite)

        # Card Network & Type
        raw_net = str(raw_payload.get("card4") or "").strip().lower()
        card_network = CARD_NETWORK_MAP.get(raw_net, CardNetwork.OTHER)

        raw_type = str(raw_payload.get("card6") or "").strip().lower()
        card_type = CARD_TYPE_MAP.get(raw_type, CardType.UNKNOWN)

        # Merchant & MCC
        prod_cd = str(raw_payload.get("ProductCD") or "W").strip()
        mcc = PRODUCT_MCC_MAP.get(prod_cd, "5311")
        merchant_id = f"merch_vesta_{prod_cd}_{addr1}"

        # Capture Vesta engineered features in metadata
        vesta_features = {}
        for key in raw_payload:
            if key.startswith(("C", "D", "M", "V", "id_", "addr", "dist", "P_", "R_")):
                vesta_features[key] = raw_payload[key]

        metadata = {
            "source_protocol": "IEEE_CIS_VESTA_TABULAR",
            "is_native_iso8583": False,
            "ProductCD": prod_cd,
            "raw_TransactionDT": dt_seconds,
            "vesta_feature_count": len(vesta_features),
            "vesta_features": vesta_features
        }

        # Device info if present
        dev_type = raw_payload.get("DeviceType")
        dev_info = raw_payload.get("DeviceInfo")
        device_fingerprint = f"{dev_type}_{dev_info}" if (dev_type or dev_info) else None

        return CanonicalTransaction(
            transaction_id=f"ieee_{tx_id}",
            timestamp=timestamp,
            amount=amount,
            currency="USD",
            card_pan_token=card_pan_token,
            card_bin=card_bin,
            card_last4=card_last4,
            card_network=card_network,
            card_type=card_type,
            merchant_id=merchant_id,
            mcc=mcc,
            merchant_country="USA",
            channel=PaymentChannel.ECOMMERCE,
            device_fingerprint=device_fingerprint,
            metadata=metadata
        )
