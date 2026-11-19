"""
FraudShield 3.0 Generic E-Commerce REST JSON Adapter.
Normalizes standard modern REST API JSON payment payloads into CanonicalTransaction models.
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone

from backend.app.v3.adapters.base import BaseTransactionAdapter
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.services.token_service import KmsTokenService


class GenericJsonAdapter(BaseTransactionAdapter):
    """
    Adapter for standard JSON payment payloads received over REST APIs.
    Accepts intuitive field names and normalizes them into CanonicalTransaction.
    """

    def __init__(self, token_service: Optional[KmsTokenService] = None):
        self.token_service = token_service or KmsTokenService()

    def get_schema_type(self) -> str:
        return "GENERIC_REST_JSON"

    def validate(self, raw_payload: Any) -> Tuple[bool, List[str]]:
        """
        Validates core JSON transaction fields.
        """
        errors = []

        if not isinstance(raw_payload, dict):
            return False, ["Payload must be a JSON dictionary"]

        # Transaction ID
        if not raw_payload.get("transaction_id"):
            errors.append("Missing mandatory 'transaction_id'")

        # Amount
        amt = raw_payload.get("amount")
        if amt is None:
            errors.append("Missing mandatory 'amount'")
        else:
            try:
                amt_float = float(amt)
                if amt_float <= 0.0:
                    errors.append(f"'amount' must be greater than zero, got {amt_float}")
            except (ValueError, TypeError):
                errors.append(f"'amount' must be a numeric value, got '{amt}'")

        # Card: either card_pan (which will be tokenized) or pre-tokenized card_pan_token
        pan = raw_payload.get("card_pan") or raw_payload.get("pan") or raw_payload.get("card_number")
        token = raw_payload.get("card_pan_token")
        if not pan and not token:
            errors.append("Must provide either 'card_pan' (for tokenization) or 'card_pan_token'")
        elif pan:
            clean_pan = "".join(filter(str.isdigit, str(pan)))
            if not self.token_service.validate_luhn(clean_pan):
                errors.append("Provided 'card_pan' failed Luhn checksum validation")

        # Merchant ID
        if not raw_payload.get("merchant_id"):
            errors.append("Missing mandatory 'merchant_id'")

        # MCC
        mcc = str(raw_payload.get("mcc") or "").strip()
        if not mcc or len(mcc) != 4 or not mcc.isdigit():
            errors.append(f"'mcc' must be a 4-digit string, got '{mcc}'")

        return len(errors) == 0, errors

    def adapt(self, raw_payload: Any) -> CanonicalTransaction:
        """
        Transforms validated JSON payload into CanonicalTransaction.
        """
        is_valid, errors = self.validate(raw_payload)
        if not is_valid:
            raise ValueError(f"Generic JSON validation failed: {'; '.join(errors)}")

        tx_id = str(raw_payload["transaction_id"]).strip()
        amount = round(float(raw_payload["amount"]), 2)
        currency = str(raw_payload.get("currency", "USD")).upper()

        # Timestamp
        ts_raw = raw_payload.get("timestamp")
        if isinstance(ts_raw, datetime):
            timestamp = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        elif isinstance(ts_raw, str):
            try:
                timestamp = datetime.fromisoformat(ts_raw)
                if not timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Card Tokenization & BIN extraction
        pan = raw_payload.get("card_pan") or raw_payload.get("pan") or raw_payload.get("card_number")
        if pan:
            clean_pan = "".join(filter(str.isdigit, str(pan)))
            pan_token = self.token_service.tokenize_pan(clean_pan)
            card_bin, card_last4 = self.token_service.extract_bin_and_last4(clean_pan)
            card_network = self.token_service.detect_network(clean_pan)
        else:
            pan_token = str(raw_payload["card_pan_token"]).strip()
            card_bin = str(raw_payload.get("card_bin", "000000")).zfill(6)[:6]
            card_last4 = str(raw_payload.get("card_last4", "0000")).zfill(4)[-4:]
            card_network = CardNetwork(raw_payload.get("card_network", CardNetwork.OTHER))

        # Channel
        raw_channel = str(raw_payload.get("channel", "ECOMMERCE")).upper()
        try:
            channel = PaymentChannel(raw_channel)
        except ValueError:
            channel = PaymentChannel.ECOMMERCE

        # Card Type
        raw_type = str(raw_payload.get("card_type", "UNKNOWN")).upper()
        try:
            card_type = CardType(raw_type)
        except ValueError:
            card_type = CardType.UNKNOWN

        # Location / Geo
        lat = float(raw_payload["latitude"]) if "latitude" in raw_payload and raw_payload["latitude"] is not None else None
        lon = float(raw_payload["longitude"]) if "longitude" in raw_payload and raw_payload["longitude"] is not None else None

        metadata = raw_payload.get("metadata", {})
        metadata["source_protocol"] = "GENERIC_REST_JSON"

        return CanonicalTransaction(
            transaction_id=tx_id,
            timestamp=timestamp,
            amount=amount,
            currency=currency,
            card_pan_token=pan_token,
            card_bin=card_bin,
            card_last4=card_last4,
            card_network=card_network,
            card_type=card_type,
            merchant_id=str(raw_payload["merchant_id"]).strip(),
            mcc=str(raw_payload["mcc"]).strip().zfill(4),
            merchant_country=str(raw_payload.get("merchant_country", "USA")).upper(),
            channel=channel,
            pos_entry_mode=str(raw_payload.get("pos_entry_mode", "05")),
            ip_address_hash=raw_payload.get("ip_address_hash"),
            device_fingerprint=raw_payload.get("device_fingerprint"),
            billing_shipping_match=raw_payload.get("billing_shipping_match"),
            cvv_result_code=raw_payload.get("cvv_result_code"),
            latitude=lat,
            longitude=lon,
            metadata=metadata
        )
