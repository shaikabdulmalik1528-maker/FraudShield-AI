"""
FraudShield 3.0 ISO 4217 Currency Normalization & FX Service (CURR-01).
Ensures that cross-currency monetary amounts are consistently normalized to base USD
prior to sliding-window velocity aggregations, spend ratios, and z-score calculations,
preventing artificial 100x baseline spikes while preserving raw transaction currencies.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Standard ISO 4217 FX Reference Rates (Units of USD per 1 Currency Unit)
DEFAULT_FX_RATES_TO_USD: Dict[str, float] = {
    "USD": 1.0000,
    "EUR": 1.0850,
    "GBP": 1.2820,
    "JPY": 0.0065,  # 1 JPY ≈ 0.0065 USD (1 USD ≈ 154 JPY)
    "CAD": 0.7410,
    "AUD": 0.6550,
    "CHF": 1.1320,
    "CNY": 0.1380,
    "INR": 0.0118,
    "KWD": 3.2500,  # 1 KWD ≈ 3.25 USD
    "SGD": 0.7480,
    "BRL": 0.1820,
    "MXN": 0.0545,
    "SEK": 0.0950,
    "NZD": 0.6050,
    "ZAR": 0.0550,
    "AED": 0.2723,
    "SAR": 0.2666,
    "HKD": 0.1285,
}


class BaseCurrencyConverter(ABC):
    """Abstract port for real-time and static foreign exchange currency converters."""

    @abstractmethod
    def convert_to_usd(self, amount: float, from_currency: str) -> float:
        """
        Converts a major unit amount from `from_currency` into base USD.
        Returns the normalized USD amount as float rounded to 4 decimal places.
        """
        pass

    @abstractmethod
    def get_rate(self, currency: str) -> Tuple[float, bool]:
        """
        Retrieves the exchange rate (USD per unit) for the given currency code.
        Returns (rate, is_fallback).
        """
        pass


class StaticFxCurrencyConverter(BaseCurrencyConverter):
    """
    High-performance thread-safe currency converter with cached FX rates,
    staleness validation, and graceful fallback handling for unknown currencies.
    """

    def __init__(
        self,
        custom_rates: Optional[Dict[str, float]] = None,
        stale_threshold_hours: float = 24.0,
        reference_time: Optional[datetime] = None
    ):
        self._rates: Dict[str, float] = dict(DEFAULT_FX_RATES_TO_USD)
        if custom_rates:
            for cur, rate in custom_rates.items():
                self._rates[cur.upper()] = float(rate)

        self._stale_threshold = timedelta(hours=stale_threshold_hours)
        self._last_updated = reference_time or datetime.now(timezone.utc)
        self.missing_currency_counts: Dict[str, int] = {}

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    def is_stale(self, current_time: Optional[datetime] = None) -> bool:
        now = current_time or datetime.now(timezone.utc)
        return (now - self._last_updated) > self._stale_threshold

    def update_rates(self, new_rates: Dict[str, float], timestamp: Optional[datetime] = None) -> None:
        """Updates internal exchange rate table with fresh market data."""
        for cur, rate in new_rates.items():
            if rate <= 0:
                raise ValueError(f"Exchange rate for {cur} must be positive, got {rate}")
            self._rates[cur.upper()] = float(rate)
        self._last_updated = timestamp or datetime.now(timezone.utc)
        logger.info("Updated FX conversion rates for %d currencies at %s", len(new_rates), self._last_updated.isoformat())

    def get_rate(self, currency: str) -> Tuple[float, bool]:
        """
        Returns (rate, is_fallback).
        If currency is not present, returns (1.0, True) and records metric.
        """
        cur = currency.upper().strip()
        if cur in self._rates:
            return self._rates[cur], False

        # Graceful fallback: log warning and use 1.0 (neutral 1:1)
        self.missing_currency_counts[cur] = self.missing_currency_counts.get(cur, 0) + 1
        logger.warning(
            "FX rate for currency '%s' not found. Falling back to 1.0 (1:1 USD equivalent). Total occurrences: %d",
            cur, self.missing_currency_counts[cur]
        )
        return 1.0, True

    def convert_to_usd(self, amount: float, from_currency: str) -> float:
        """
        Converts transaction amount to base USD.
        Preserves 0.0 or negative values correctly.
        """
        if amount == 0.0:
            return 0.0

        rate, _ = self.get_rate(from_currency)
        converted = float(amount) * rate
        return round(converted, 4)


# Global default converter instance
default_currency_converter = StaticFxCurrencyConverter()
