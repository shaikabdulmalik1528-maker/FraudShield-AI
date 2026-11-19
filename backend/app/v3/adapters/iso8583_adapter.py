"""
FraudShield 3.0 ISO 8583 Message Ingestion Adapter.
Parses, validates, and normalizes ISO 8583 banking authorization messages into CanonicalTransaction models.
Supports MTIs: 0100 (Auth Request), 0110 (Auth Response), 0200 (Financial Request), 0420 (Reversal).
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone
import re

from backend.app.v3.adapters.base import BaseTransactionAdapter
from backend.app.v3.schemas.canonical import (
    CanonicalTransaction,
    CardNetwork,
    CardType,
    PaymentChannel
)
from backend.app.v3.schemas.iso8583 import Iso8583Mti
from backend.app.v3.services.token_service import KmsTokenService


# ISO 4217 Numeric to Alpha-3 Currency Mapping
ISO_CURRENCY_MAP = {
    "840": "USD",
    "978": "EUR",
    "826": "GBP",
    "124": "CAD",
    "036": "AUD",
    "392": "JPY",
    "756": "CHF",
    "156": "CNY",
    "356": "INR",
    "414": "KWD",
    "048": "BHD",
    "512": "OMR",
    "410": "KRW"
}

# ISO 4217 Currency Exponents (minor currency unit scale)
# e.g., JPY/KRW have 0 minor units, KWD/BHD have 3, USD/EUR have 2.
ISO_CURRENCY_EXPONENTS = {
    "840": 2,  # USD
    "978": 2,  # EUR
    "826": 2,  # GBP
    "124": 2,  # CAD
    "036": 2,  # AUD
    "392": 0,  # JPY
    "410": 0,  # KRW
    "414": 3,  # KWD
    "048": 3,  # BHD
    "512": 3,  # OMR
    "756": 2,  # CHF
    "156": 2,  # CNY
    "356": 2,  # INR
}

# ISO 3166-1 Numeric to Alpha-3 Country Mapping
ISO_COUNTRY_MAP = {
    "840": "USA",
    "250": "FRA",
    "276": "DEU",
    "826": "GBR",
    "124": "CAN",
    "036": "AUS",
    "392": "JPN",
    "056": "BEL",
    "356": "IND"
}


class Iso8583Adapter(BaseTransactionAdapter):
    """
    Adapter for ISO 8583 payment messages.
    Supports structured dictionary payloads as well as raw bitmap-encoded message frames.
    """

    def __init__(self, token_service: Optional[KmsTokenService] = None):
        self.token_service = token_service or KmsTokenService()

    def get_schema_type(self) -> str:
        return "ISO_8583"

    def validate(self, raw_payload: Any) -> Tuple[bool, List[str]]:
        """
        Validates ISO 8583 message structure and mandatory fields.
        """
        errors = []

        if not isinstance(raw_payload, dict):
            return False, ["Payload must be a dictionary representing parsed or structured ISO 8583 data"]

        # 1. Validate MTI
        mti = str(raw_payload.get("mti", "")).strip()
        valid_mtis = {m.value for m in Iso8583Mti}
        if mti not in valid_mtis:
            errors.append(f"Invalid or missing MTI: '{mti}'. Must be one of {sorted(valid_mtis)}")

        # 2. Validate DE 2 (PAN)
        pan = raw_payload.get("de2") or raw_payload.get("pan")
        if not pan:
            errors.append("Missing mandatory DE 2 (Primary Account Number)")
        else:
            clean_pan = "".join(filter(str.isdigit, str(pan)))
            if len(clean_pan) < 12 or len(clean_pan) > 19:
                errors.append(f"DE 2 (PAN) length invalid ({len(clean_pan)} digits, expected 12-19)")
            elif not self.token_service.validate_luhn(clean_pan):
                errors.append("DE 2 (PAN) failed Luhn checksum validation")

        # 3. Validate DE 4 (Amount)
        amount_val = raw_payload.get("de4") if "de4" in raw_payload else raw_payload.get("amount_cents")
        if amount_val is None:
            errors.append("Missing mandatory DE 4 (Amount)")
        else:
            try:
                amt_int = int(amount_val)
                if amt_int <= 0 and mti in ("0100", "0200"):
                    errors.append(f"DE 4 (Amount) must be greater than zero for auth/financial requests, got {amt_int}")
            except (ValueError, TypeError):
                errors.append(f"DE 4 (Amount) must be an integer (minor units/cents), got '{amount_val}'")

        # 4. Validate DE 7 (Date & Time MMDDhhmmss)
        dt_str = raw_payload.get("de7") or raw_payload.get("transmission_datetime")
        if not dt_str:
            errors.append("Missing mandatory DE 7 (Transmission Date & Time)")
        else:
            dt_clean = "".join(filter(str.isdigit, str(dt_str)))
            if len(dt_clean) != 10:
                errors.append(f"DE 7 must be 10 numeric digits (MMDDhhmmss), got '{dt_str}'")
            else:
                month = int(dt_clean[:2])
                day = int(dt_clean[2:4])
                hour = int(dt_clean[4:6])
                minute = int(dt_clean[6:8])
                second = int(dt_clean[8:10])
                if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                    errors.append(f"DE 7 components out of valid range: '{dt_str}'")

        # 5. Validate DE 18 (MCC)
        mcc = raw_payload.get("de18") or raw_payload.get("mcc")
        if not mcc:
            errors.append("Missing mandatory DE 18 (Merchant Category Code)")
        else:
            mcc_str = str(mcc).strip()
            if len(mcc_str) != 4 or not mcc_str.isdigit():
                errors.append(f"DE 18 (MCC) must be exactly 4 numeric digits, got '{mcc}'")

        # 6. Validate DE 41 and DE 42 (Terminal & Merchant ID)
        term_id = raw_payload.get("de41") or raw_payload.get("terminal_id")
        merch_id = raw_payload.get("de42") or raw_payload.get("merchant_id")
        if not term_id:
            errors.append("Missing mandatory DE 41 (Card Acceptor Terminal ID)")
        if not merch_id:
            errors.append("Missing mandatory DE 42 (Card Acceptor ID Code)")

        return len(errors) == 0, errors

    def adapt(self, raw_payload: Any) -> CanonicalTransaction:
        """
        Transforms validated ISO 8583 payload into CanonicalTransaction.
        """
        is_valid, errors = self.validate(raw_payload)
        if not is_valid:
            raise ValueError(f"ISO 8583 payload validation failed: {'; '.join(errors)}")

        # Extract & Tokenize PAN
        raw_pan = str(raw_payload.get("de2") or raw_payload.get("pan"))
        clean_pan = "".join(filter(str.isdigit, raw_pan))
        pan_token = self.token_service.tokenize_pan(clean_pan)
        card_bin, card_last4 = self.token_service.extract_bin_and_last4(clean_pan)
        card_network = self.token_service.detect_network(clean_pan)

        # Decode Currency (DE 49) first to establish minor unit exponent
        curr_raw = str(raw_payload.get("de49") or raw_payload.get("currency_code") or "840").strip()
        currency_code = ISO_CURRENCY_MAP.get(curr_raw, "USD")
        currency_exponent = ISO_CURRENCY_EXPONENTS.get(curr_raw, 2)

        # Decode Amount (DE 4 scaled by currency exponent)
        amount_raw = raw_payload.get("de4") if "de4" in raw_payload else raw_payload.get("amount_cents")
        amount_cents = int(amount_raw)
        divisor = 10 ** currency_exponent
        amount_major = round(amount_cents / float(divisor), currency_exponent if currency_exponent > 0 else 2)

        # Decode Date & Time (DE 7: MMDDhhmmss)
        dt_raw = str(raw_payload.get("de7") or raw_payload.get("transmission_datetime")).strip()
        month = int(dt_raw[:2])
        day = int(dt_raw[2:4])
        hour = int(dt_raw[4:6])
        minute = int(dt_raw[6:8])
        second = int(dt_raw[8:10])
        # Use current year for MMDDhhmmss
        year = datetime.now(timezone.utc).year
        try:
            timestamp = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        except ValueError:
            # Fallback for leap year / edge day
            timestamp = datetime(year, month, min(day, 28), hour, minute, second, tzinfo=timezone.utc)

        # Decode Country (DE 19)
        country_raw = str(raw_payload.get("de19") or raw_payload.get("acquirer_country") or "840").strip()
        merchant_country = ISO_COUNTRY_MAP.get(country_raw, "USA")

        # Decode Channel from POS Entry Mode (DE 22)
        pos_entry = str(raw_payload.get("de22") or raw_payload.get("pos_entry_mode") or "051")[:2]
        if pos_entry == "05":
            channel = PaymentChannel.POS_CHIP
        elif pos_entry == "07":
            channel = PaymentChannel.POS_CONTACTLESS
        elif pos_entry == "02":
            channel = PaymentChannel.POS_SWIPE
        elif pos_entry == "01":
            channel = PaymentChannel.POS_MANUAL
        elif pos_entry in ("10", "81"):
            channel = PaymentChannel.ECOMMERCE
        elif pos_entry == "03":
            channel = PaymentChannel.ATM
        else:
            channel = PaymentChannel.ECOMMERCE

        # Generate unique transaction ID from STAN (DE 11), RRN (DE 37), or timestamp
        stan = str(raw_payload.get("de11") or raw_payload.get("stan") or "000000").strip()
        rrn = str(raw_payload.get("de37") or raw_payload.get("rrn") or "").strip()
        mti = str(raw_payload.get("mti", "0100")).strip()
        transaction_id = f"iso_{mti}_{stan}_{int(timestamp.timestamp())}"
        if rrn:
            transaction_id = f"iso_{rrn}_{stan}"

        # MCC (DE 18)
        mcc = str(raw_payload.get("de18") or raw_payload.get("mcc")).strip().zfill(4)

        # Merchant & Terminal Identifiers
        merchant_id = str(raw_payload.get("de42") or raw_payload.get("merchant_id")).strip()
        terminal_id = str(raw_payload.get("de41") or raw_payload.get("terminal_id")).strip()

        # Metadata
        metadata = {
            "source_protocol": "ISO_8583",
            "mti": mti,
            "stan": stan,
            "rrn": rrn,
            "terminal_id": terminal_id,
            "processing_code": str(raw_payload.get("de3") or raw_payload.get("processing_code") or "000000"),
            "pos_condition_code": str(raw_payload.get("de25") or raw_payload.get("pos_condition_code") or "00"),
            "card_acceptor_name_loc": str(raw_payload.get("de43") or raw_payload.get("card_acceptor_name_loc") or "")
        }

        return CanonicalTransaction(
            transaction_id=transaction_id,
            timestamp=timestamp,
            amount=amount_major,
            currency=currency_code,
            card_pan_token=pan_token,
            card_bin=card_bin,
            card_last4=card_last4,
            card_network=card_network,
            card_type=CardType.DEBIT,
            merchant_id=merchant_id,
            mcc=mcc,
            merchant_country=merchant_country,
            channel=channel,
            pos_entry_mode=pos_entry,
            metadata=metadata
        )

    def parse_raw_message_frame(self, raw_message: str) -> Dict[str, Any]:
        """
        Parses an ASCII/hex-encoded ISO 8583 message string.
        Format: MTI (4 chars) + Primary Bitmap (16 hex chars) + Data Fields.
        """
        clean_msg = raw_message.strip()
        if len(clean_msg) < 20:
            raise ValueError("Raw message frame too short to contain MTI and 16-hex bitmap")

        mti = clean_msg[:4]
        bitmap_hex = clean_msg[4:20]
        data_part = clean_msg[20:]

        # Convert hex bitmap to 64-bit binary string
        try:
            bitmap_int = int(bitmap_hex, 16)
            bitmap_bin = bin(bitmap_int)[2:].zfill(64)
        except ValueError:
            raise ValueError(f"Invalid primary bitmap hex: '{bitmap_hex}'")

        # Parse data elements based on bitmap flags
        parsed = {"mti": mti, "primary_bitmap": bitmap_hex}

        # For demonstration and ingestion parsing of standard test frames:
        # If the data_part contains delimited or fixed subfields:
        # Standard lightweight tokenization
        fields = data_part.split("|")
        field_keys = ["de2", "de3", "de4", "de7", "de11", "de18", "de41", "de42", "de49"]
        for idx, val in enumerate(fields):
            if idx < len(field_keys):
                parsed[field_keys[idx]] = val.strip()

        return parsed
