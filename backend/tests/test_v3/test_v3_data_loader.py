"""
Unit tests for FraudShield 3.0 IEEE-CIS Data Loader & Benchmark Generator.
Verifies schema conformity, fraud prevalence, and temporal progression.
"""

import pytest
import pandas as pd
import numpy as np
from backend.app.v3.ml.data_loader import generate_ieee_cis_benchmark, load_ieee_cis_dataset


def test_generate_ieee_cis_benchmark_schema():
    """Asserts that synthesized benchmark matches IEEE-CIS schema and distributions."""
    n_samples = 1000
    df = generate_ieee_cis_benchmark(n_samples=n_samples, random_state=42)

    assert len(df) == n_samples
    assert "TransactionID" in df.columns
    assert "isFraud" in df.columns
    assert "TransactionDT" in df.columns
    assert "TransactionAmt" in df.columns
    assert "ProductCD" in df.columns
    assert "card1" in df.columns
    assert "card4" in df.columns
    assert "card6" in df.columns

    # Verify fraud prevalence (~3.5%)
    fraud_rate = df["isFraud"].mean()
    assert 0.02 <= fraud_rate <= 0.055

    # Verify monotonic time progression
    assert (np.diff(df["TransactionDT"]) >= 0).all()

    # Verify amount bounds
    assert (df["TransactionAmt"] > 0).all()


def test_load_ieee_cis_dataset_synthetic_fallback(tmp_path):
    """Asserts that loader returns (X, y) with consistent shapes."""
    X, y = load_ieee_cis_dataset(data_dir=tmp_path / "raw", cache_dir=tmp_path / "cache", sample_size=500, force_synthetic=True)

    assert isinstance(X, pd.DataFrame)
    assert isinstance(y, pd.Series)
    assert len(X) == 500
    assert len(y) == 500
    assert "isFraud" not in X.columns
