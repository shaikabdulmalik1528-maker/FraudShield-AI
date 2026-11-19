"""
FraudShield 3.0 Leakage-Free Temporal Splitting & Feature Preprocessing Engine.
Enforces purged & embargoed time-series data splits, native integer categorical encoding,
temporal cyclical encodings, and cardholder behavioral baseline features.
"""

import logging
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

logger = logging.getLogger(__name__)


def temporal_train_val_test_split(
    df: pd.DataFrame,
    y: pd.Series,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    embargo_seconds: int = 86400  # 24-hour embargo gap
) -> Tuple[Tuple[pd.DataFrame, pd.Series], Tuple[pd.DataFrame, pd.Series], Tuple[pd.DataFrame, pd.Series]]:
    """
    Splits dataset chronologically based on TransactionDT with 24-hour embargo buffers
    between Train/Val and Val/Test to prevent boundary leakage and lookahead bias.
    """
    logger.info("Executing purged & embargoed chronological split (embargo=%ds)...", embargo_seconds)

    # Sort strictly by time
    sort_idx = np.argsort(df["TransactionDT"].values)
    df_sorted = df.iloc[sort_idx].reset_index(drop=True)
    y_sorted = y.iloc[sort_idx].reset_index(drop=True)

    min_t = df_sorted["TransactionDT"].min()
    max_t = df_sorted["TransactionDT"].max()
    total_span = max_t - min_t

    train_end_t = min_t + (total_span * train_ratio)
    val_start_t = train_end_t + embargo_seconds
    val_end_t = val_start_t + (total_span * val_ratio)
    test_start_t = val_end_t + embargo_seconds

    train_mask = df_sorted["TransactionDT"] <= train_end_t
    val_mask = (df_sorted["TransactionDT"] >= val_start_t) & (df_sorted["TransactionDT"] <= val_end_t)
    test_mask = df_sorted["TransactionDT"] >= test_start_t

    X_train, y_train = df_sorted[train_mask].copy(), y_sorted[train_mask].copy()
    X_val, y_val = df_sorted[val_mask].copy(), y_sorted[val_mask].copy()
    X_test, y_test = df_sorted[test_mask].copy(), y_sorted[test_mask].copy()

    logger.info(
        "Temporal Split Summary: Train N=%d (fraud=%.3f%%) | Val N=%d (fraud=%.3f%%) | Test N=%d (fraud=%.3f%%)",
        len(X_train), y_train.mean() * 100,
        len(X_val), y_val.mean() * 100,
        len(X_test), y_test.mean() * 100
    )

    return (X_train, y_train), (X_val, y_val), (X_test, y_test)


class IeeeCisPreprocessor(BaseEstimator, TransformerMixin):
    """
    Leakage-free feature engineering and preprocessing transformer for IEEE-CIS data.
    All encoders and baseline aggregates are fitted strictly on the Training split.
    """

    CATEGORICAL_COLUMNS = [
        "ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain",
        "DeviceType", "DeviceInfo",
        "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"
    ]

    NUMERIC_COLUMNS_BASE = [
        "TransactionAmt", "dist1", "card1", "card2", "card3", "card5", "addr1", "addr2"
    ]

    def __init__(self, correlation_threshold: float = 0.90):
        self.correlation_threshold = correlation_threshold
        self.cat_mappings: Dict[str, Dict[str, int]] = {}
        self.card_spend_mean: Dict[Any, float] = {}
        self.card_tx_count: Dict[Any, int] = {}
        self.global_mean_spend: float = 0.0
        self.selected_v_features: List[str] = []
        self.feature_names_: List[str] = []
        self.categorical_features_: List[str] = []

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        """Fits encoders, baseline card stats, and feature selectors strictly on training data."""
        df = X.copy()

        # 1. Fit categorical integer mappings
        self.cat_mappings = {}
        for col in self.CATEGORICAL_COLUMNS:
            if col in df.columns:
                unique_vals = [v for v in df[col].dropna().unique()]
                # Map to 0, 1, 2, ...
                mapping = {val: idx for idx, val in enumerate(sorted(unique_vals))}
                self.cat_mappings[col] = mapping

        # 2. Fit cardholder baseline spend statistics
        self.global_mean_spend = float(df["TransactionAmt"].mean())
        if "card1" in df.columns:
            self.card_spend_mean = df.groupby("card1")["TransactionAmt"].mean().to_dict()
            self.card_tx_count = df.groupby("card1")["TransactionID"].count().to_dict()

        # 3. Filter redundant collinear V-features
        v_cols = [c for c in df.columns if c.startswith("V") and c[1:].isdigit()]
        if v_cols:
            # Subsample correlation check for performance
            corr_sample = df[v_cols].sample(min(5000, len(df)), random_state=42).fillna(0)
            corr_matrix = corr_sample.corr().abs()
            upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
            to_drop = [col for col in upper_tri.columns if any(upper_tri[col] > self.correlation_threshold)]
            self.selected_v_features = [c for c in v_cols if c not in to_drop]
            logger.info("V-features pruned from %d to %d (threshold=%.2f)", len(v_cols), len(self.selected_v_features), self.correlation_threshold)
        else:
            self.selected_v_features = []

        # Record target column list
        transformed_sample = self._transform_internal(df.head(5))
        self.feature_names_ = list(transformed_sample.columns)
        self.categorical_features_ = [c for c in self.feature_names_ if c in self.cat_mappings or c == "card_bin_cat"]

        return self

    def _transform_internal(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)

        # 1. Cyclical Temporal Encodings from TransactionDT
        # In IEEE-CIS, TransactionDT is in seconds
        dt = df["TransactionDT"].values
        hours = (dt / 3600.0) % 24.0
        dow = (dt / (3600.0 * 24.0)) % 7.0

        out["hour_sin"] = np.round(np.sin(2.0 * np.pi * hours / 24.0), 4)
        out["hour_cos"] = np.round(np.cos(2.0 * np.pi * hours / 24.0), 4)
        out["dow_sin"] = np.round(np.sin(2.0 * np.pi * dow / 7.0), 4)
        out["dow_cos"] = np.round(np.cos(2.0 * np.pi * dow / 7.0), 4)

        # 2. Transaction Amount and Spend Deviation Ratios
        amt = df["TransactionAmt"].values
        out["TransactionAmt"] = amt
        out["TransactionAmt_log"] = np.log1p(amt)

        # Cardholder Baseline Deviation
        if "card1" in df.columns:
            card_means = df["card1"].map(self.card_spend_mean).fillna(self.global_mean_spend).values
            out["amount_ratio_baseline"] = np.round(amt / np.maximum(card_means, 0.01), 4)
            out["card_tx_count_historical"] = df["card1"].map(self.card_tx_count).fillna(0).values.astype(np.float32)

        # 3. Categorical Encodings (Non-negative Integer Codes for LightGBM)
        for col in self.CATEGORICAL_COLUMNS:
            if col in df.columns:
                mapping = self.cat_mappings.get(col, {})
                unknown_code = len(mapping)
                # Map to non-negative integer; unseen/NaN categories mapped to unknown_code
                encoded = df[col].map(mapping).fillna(unknown_code).astype(np.int32)
                out[col] = encoded

        # 4. Numeric & C-Features (Counts / Velocity Proxies)
        c_cols = [c for c in df.columns if c.startswith("C") and c[1:].isdigit()]
        for col in c_cols:
            out[col] = df[col].astype(np.float32)

        # 5. D-Features (Timedeltas)
        d_cols = [c for c in df.columns if c.startswith("D") and c[1:].isdigit()]
        for col in d_cols:
            out[col] = df[col].astype(np.float32)

        # 6. Selected Non-Collinear V-Features
        for col in self.selected_v_features:
            if col in df.columns:
                out[col] = df[col].astype(np.float32)

        # 7. Additional Base Numeric Columns (addr, dist)
        for col in ["dist1", "card2", "card3", "card5", "addr1", "addr2"]:
            if col in df.columns:
                out[col] = df[col].astype(np.float32)

        return out

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transforms input DataFrame into model feature matrix."""
        return self._transform_internal(X)

    def transform_single_enriched(self, enriched_vector: Any) -> np.ndarray:
        """
        Fast-path single-transaction feature vector generator for sub-millisecond inference.
        Directly evaluates cyclical temporal encodings, log transforms, and categorical mappings
        into a pre-indexed 2D numpy array (shape 1 x 89) matching self.feature_names_ exactly.
        Bypasses 400-column intermediate pandas DataFrame instantiation.
        """
        dt = int(enriched_vector.timestamp.timestamp())
        hours = (dt / 3600.0) % 24.0
        dow = (dt / (3600.0 * 24.0)) % 7.0
        amt = float(enriched_vector.amount)

        def _get_cat(col: str, val: Any) -> float:
            mapping = self.cat_mappings.get(col, {})
            return float(mapping.get(val, len(mapping)))

        channel_device = "desktop" if enriched_vector.channel == "ECOMMERCE" else "mobile"

        d = {
            "hour_sin": round(float(np.sin(2.0 * np.pi * hours / 24.0)), 4),
            "hour_cos": round(float(np.cos(2.0 * np.pi * hours / 24.0)), 4),
            "dow_sin": round(float(np.sin(2.0 * np.pi * dow / 7.0)), 4),
            "dow_cos": round(float(np.cos(2.0 * np.pi * dow / 7.0)), 4),
            "TransactionAmt": amt,
            "TransactionAmt_log": float(np.log1p(amt)),
            "amount_ratio_baseline": float(enriched_vector.card_amount_ratio_30d),
            "card_tx_count_historical": float(enriched_vector.card_tx_count_1h),
            "ProductCD": _get_cat("ProductCD", "W"),
            "card4": _get_cat("card4", enriched_vector.card_network.lower()),
            "card6": _get_cat("card6", enriched_vector.card_type.lower()),
            "P_emaildomain": _get_cat("P_emaildomain", "gmail.com"),
            "R_emaildomain": _get_cat("R_emaildomain", "gmail.com"),
            "DeviceType": _get_cat("DeviceType", channel_device),
            "DeviceInfo": _get_cat("DeviceInfo", "FraudShield POS Terminal v3"),
            "C1": float(enriched_vector.card_tx_count_1h),
            "C2": float(enriched_vector.card_tx_count_24h),
            "C3": float(enriched_vector.card_tx_count_7d),
            "C4": 0.0,
            "C5": 0.0,
            "C6": 1.0,
            "C7": 0.0,
            "C8": 0.0,
            "C9": 1.0,
            "C10": 0.0,
            "C11": 1.0,
            "C12": 0.0,
            "C13": float(enriched_vector.merchant_tx_count_1h),
            "C14": float(enriched_vector.merchant_tx_count_24h),
            "dist1": float(enriched_vector.distance_km) if enriched_vector.distance_km is not None else 10.0,
            "card2": 321.0,
            "card3": 150.0,
            "card5": 226.0,
            "addr1": 299.0,
            "addr2": 87.0
        }
        for i in range(1, 10):
            d[f"M{i}"] = _get_cat(f"M{i}", "T")
        for i in range(1, 16):
            d[f"D{i}"] = 1.0
        for i in range(1, 31):
            d[f"V{i}"] = 1.0

        vec = [d.get(col, 0.0) for col in self.feature_names_]
        return np.array([vec], dtype=np.float64)
