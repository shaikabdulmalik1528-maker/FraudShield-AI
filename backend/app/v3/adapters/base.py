"""
FraudShield 3.0 Hexagonal Adapter Port Interface.
Defines abstract contracts for all raw payment message adapters.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List
from backend.app.v3.schemas.canonical import CanonicalTransaction


class BaseTransactionAdapter(ABC):
    """
    Abstract port interface for incoming transaction payloads.
    Every concrete adapter must implement schema validation and normalization
    into the immutable CanonicalTransaction domain entity.
    """

    @abstractmethod
    def validate(self, raw_payload: Any) -> Tuple[bool, List[str]]:
        """
        Validates the incoming raw payload against the adapter's structural rules.
        Returns:
            (is_valid: bool, error_messages: List[str])
        """
        pass

    @abstractmethod
    def adapt(self, raw_payload: Any) -> CanonicalTransaction:
        """
        Transforms the validated raw payload into the standardized CanonicalTransaction model.
        Raises ValueError if the payload is malformed or invalid.
        """
        pass

    @abstractmethod
    def get_schema_type(self) -> str:
        """
        Returns the unique identifier for this adapter schema (e.g. 'ISO_8583', 'IEEE_CIS', 'GENERIC_JSON').
        """
        pass
