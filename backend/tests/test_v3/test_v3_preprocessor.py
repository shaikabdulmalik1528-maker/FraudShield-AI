"""
Unit tests for FraudShield 3.0 Preprocessor & Leakage-Free Temporal Splitter.
Verifies purged/embargoed split boundaries, categorical integer encoding, and cyclical temporal encodings.
"""

import pytest
import numpy as np
import pandas as pd
from backend.app.v3.ml.data_loader import generate_ieee_cis_benchmark
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split, IeeeCisPreprocessor


def test_purged_embargoed_temporal_split():
    """Asserts that temporal split preserves chronological order with 24h embargo buffers."""
    df = generate_ieee_cis_benchmark(n_samples=2000, random_state=42)
    y = df.pop("isFraud")

    embargo = 86400  # 24 hours
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = temporal_train_val_test_split(
        df=df,
        y=y,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        embargo_seconds=embargo
    )

    # 1. Non-empty splits
    assert len(X_train) > 0
    assert len(X_val) > 0
    assert len(X_test) > 0

    # 2. Strict chronological boundaries
    assert X_train["TransactionDT"].max() < X_val["TransactionDT"].min()
    assert X_val["TransactionDT"].max() < X_test["TransactionDT"].min()

    # 3. 24h Embargo gap verification (zero boundary leakage)
    val_gap = X_val["TransactionDT"].min() - X_train["TransactionDT"].max()
    test_gap = X_test["TransactionDT"].min() - X_val["TransactionDT"].max()

    assert val_gap >= embargo
    assert test_gap >= embargo


def test_ieeecis_preprocessor_transformation():
    """Asserts that preprocessor produces clean feature matrices with native integer categoricals."""
    df = generate_ieee_cis_benchmark(n_samples=1000, random_state=42)
    y = df.pop("isFraud")

    (X_train, y_train), (X_val, y_val), _ = temporal_train_val_test_split(df, y, embargo_seconds=1000)

    preprocessor = IeeeCisPreprocessor()
    preprocessor.fit(X_train, y_train)

    X_train_trans = preprocessor.transform(X_train)
    X_val_trans = preprocessor.transform(X_val)

    # Verify cyclical encodings
    assert "hour_sin" in X_train_trans.columns
    assert "hour_cos" in X_train_trans.columns
    assert "dow_sin" in X_train_trans.columns
    assert "dow_cos" in X_train_trans.columns

    # Verify unit circle bound
    hour_norm = X_train_trans["hour_sin"] ** 2 + X_train_trans["hour_cos"] ** 2
    assert (np.abs(hour_norm - 1.0) < 0.01).all()

    # Verify categorical features are integer-encoded
    assert "ProductCD" in preprocessor.categorical_features_
    assert np.issubdtype(X_train_trans["ProductCD"].dtype, np.integer)

    # Verify baseline spend ratio
    assert "amount_ratio_baseline" in X_train_trans.columns
    assert (X_train_trans["amount_ratio_baseline"] >= 0).all()

    # Verify shapes match
    assert X_train_trans.shape[1] == X_val_trans.shape[1]
