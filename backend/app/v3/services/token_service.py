"""
FraudShield 3.0 Card Tokenization & Sanitization Service.
Implements PCI-DSS Level 1 compliant salted HMAC-SHA256 tokenization.
Guarantees: Zero storage or logging of cleartext Primary Account Numbers (PAN).
"""

import hmac
import hashlib
import os
import warnings
from typing import Tuple, Optional, Callable
from backend.app.v3.schemas.canonical import CardNetwork, CardType


class KmsTokenService:
    """
    Cryptographic tokenization service for payment card numbers.
    Utilizes salted HMAC-SHA256 to produce deterministic tokens for
    sliding-window velocity tracking while preventing PAN recovery.
    """

    DEFAULT_DEV_SALT = "fraudshield-enterprise-v3-secret-salt-2026"

    def __init__(
        self,
        salt_key: Optional[str] = None,
        key_provider: Optional[Callable[[], str]] = None,
        enforce_configured_salt: bool = False
    ):
        # Resolve salt from provider, direct parameter, or environment
        resolved_salt = None
        if key_provider is not None:
            resolved_salt = key_provider()
        elif salt_key is not None:
            resolved_salt = salt_key
        else:
            resolved_salt = os.environ.get("FRAUDSHIELD_TOKEN_SALT")

        is_production = os.environ.get("FRAUDSHIELD_ENV", "development").lower() in ("production", "prod")

        if not resolved_salt:
            if enforce_configured_salt or is_production:
                raise RuntimeError(
                    "Production configuration failure: KmsTokenService requires an explicit "
                    "KMS key provider or FRAUDSHIELD_TOKEN_SALT environment secret. "
                    "Insecure default fallback is prohibited in production."
                )
            warnings.warn(
                "KmsTokenService: Using default development salt. Do not use in production.",
                RuntimeWarning,
                stacklevel=2
            )
            resolved_salt = self.DEFAULT_DEV_SALT

        self._salt_key = resolved_salt.encode("utf-8")
        self.is_custom_salt = (resolved_salt != self.DEFAULT_DEV_SALT)

    @staticmethod
    def validate_luhn(pan: str) -> bool:
        """
        Validates Primary Account Number (PAN) using the standard Luhn (Mod 10) algorithm.
        """
        digits = [int(d) for d in pan if d.isdigit()]
        if len(digits) < 12 or len(digits) > 19:
            return False

        checksum = 0
        reverse_digits = digits[::-1]
        for idx, digit in enumerate(reverse_digits):
            if idx % 2 == 1:
                doubled = digit * 2
                checksum += (doubled - 9) if doubled > 9 else doubled
            else:
                checksum += digit

        return (checksum % 10) == 0

    def tokenize_pan(self, pan: str) -> str:
        """
        Computes a deterministic, irreversible HMAC-SHA256 token for the card PAN.
        Format: 'tok_v3_' followed by 32 hex characters.
        """
        clean_pan = "".join(filter(str.isdigit, str(pan)))
        if not clean_pan:
            raise ValueError("PAN must contain numeric digits")

        digest = hmac.new(self._salt_key, clean_pan.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"tok_v3_{digest[:32]}"

    @staticmethod
    def extract_bin_and_last4(pan: str) -> Tuple[str, str]:
        """
        Extracts the Bank Identification Number (BIN, first 6 digits) and last 4 digits.
        """
        clean_pan = "".join(filter(str.isdigit, str(pan)))
        if len(clean_pan) < 10:
            raise ValueError(f"PAN length must be at least 10 digits for BIN/last4 extraction, got {len(clean_pan)}")

        card_bin = clean_pan[:6]
        card_last4 = clean_pan[-4:]
        return card_bin, card_last4

    @staticmethod
    def detect_network(pan: str) -> CardNetwork:
        """
        Detects card payment network from PAN IIN prefix rules.
        """
        clean_pan = "".join(filter(str.isdigit, str(pan)))
        if not clean_pan:
            return CardNetwork.OTHER

        if clean_pan.startswith("4"):
            return CardNetwork.VISA
        elif clean_pan.startswith(("34", "37")):
            return CardNetwork.AMEX
        elif clean_pan.startswith(("6011", "65")) or clean_pan[:3] in ("644", "645"):
            return CardNetwork.DISCOVER
        elif clean_pan.startswith(("3528", "3589")):
            return CardNetwork.JCB
        elif clean_pan.startswith(("36", "38")) or (300 <= int(clean_pan[:3] or 0) <= 305):
            return CardNetwork.DINERS
        elif clean_pan.startswith("62"):
            return CardNetwork.UNIONPAY
        else:
            # Mastercard: 51-55 or 2221-2720
            prefix2 = int(clean_pan[:2] or 0)
            prefix4 = int(clean_pan[:4] or 0)
            if 51 <= prefix2 <= 55 or 2221 <= prefix4 <= 2720:
                return CardNetwork.MASTERCARD

        return CardNetwork.OTHER

    @staticmethod
    def mask_pan(pan: str) -> str:
        """
        Returns PCI-compliant masked PAN string, e.g. '4532XXXXXXXX1234'.
        """
        clean_pan = "".join(filter(str.isdigit, str(pan)))
        if len(clean_pan) < 10:
            return "XXXXXXXXXXXX"
        first6 = clean_pan[:6]
        last4 = clean_pan[-4:]
        masked_count = len(clean_pan) - 10
        return f"{first6}{'X' * masked_count}{last4}"
