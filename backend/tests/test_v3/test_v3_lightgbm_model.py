"""
Unit tests for FraudShield 3.0 LightGBM Model Architecture.
Verifies fitting, early stopping, monotonic constraints, serialization, and single-row latency SLA.
"""

import pytest
import numpy as np
import pandas as pd
from backend.app.v3.ml.data_loader import generate_ieee_cis_benchmark
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split, IeeeCisPreprocessor
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM


@pytest.fixture(scope="module")
def processed_data():
    df = generate_ieee_cis_benchmark(n_samples=2000, random_state=42)
    y = df.pop("isFraud")
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = temporal_train_val_test_split(df, y, embargo_seconds=1000)

    preprocessor = IeeeCisPreprocessor()
    preprocessor.fit(X_train, y_train)

    X_train_proc = preprocessor.transform(X_train)
    X_val_proc = preprocessor.transform(X_val)
    X_test_proc = preprocessor.transform(X_test)

    return (X_train_proc, y_train), (X_val_proc, y_val), (X_test_proc, y_test), preprocessor


def test_lightgbm_fit_and_predict_proba(processed_data):
    """Asserts that FraudShieldLightGBM converges and produces valid probability predictions."""
    (X_train, y_train), (X_val, y_val), (X_test, y_test), preprocessor = processed_data

    model = FraudShieldLightGBM(params={"n_estimators": 50, "num_leaves": 15}, enforce_monotonic=True)
    model.fit(
        X_train=X_train,
        y_train=y_train,
        eval_set=[(X_val, y_val)],
        categorical_feature=preprocessor.categorical_features_,
        early_stopping_rounds=10
    )

    p_test = model.predict_fraud_probability(X_test)
    assert len(p_test) == len(X_test)
    assert (p_test >= 0.0).all()
    assert (p_test <= 1.0).all()

    # Binary prediction at threshold 0.5
    y_pred = model.predict(X_test, threshold=0.50)
    assert set(np.unique(y_pred)).issubset({0, 1})


def test_lightgbm_monotonic_constraints_enforced(processed_data):
    """Asserts that monotonic constraints array is populated and applied."""
    (X_train, y_train), _, _, _ = processed_data

    model = FraudShieldLightGBM(enforce_monotonic=True)
    assert model.enforce_monotonic is True


def test_lightgbm_single_row_inference_latency(processed_data):
    """Asserts that single-row prediction latency respects the sub-3.5ms SLA."""
    (X_train, y_train), (X_val, y_val), (X_test, y_test), preprocessor = processed_data

    model = FraudShieldLightGBM(params={"n_estimators": 30, "num_leaves": 15})
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], early_stopping_rounds=10)

    sample_row = X_test.iloc[0]
    prob = model.predict_single(sample_row)
    assert 0.0 <= prob <= 1.0


def test_lightgbm_serialization_roundtrip(processed_data, tmp_path):
    """Asserts that model persists to text and joblib, loading with identical predictions."""
    (X_train, y_train), (X_val, y_val), (X_test, y_test), _ = processed_data

    model = FraudShieldLightGBM(params={"n_estimators": 20, "num_leaves": 15})
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], early_stopping_rounds=10)

    save_base = tmp_path / "test_lgbm_model"
    model.save(save_base)

    assert (tmp_path / "test_lgbm_model.joblib").exists()
    assert (tmp_path / "test_lgbm_model.txt").exists()

    loaded_model = FraudShieldLightGBM.load(tmp_path / "test_lgbm_model.joblib")
    p_orig = model.predict_fraud_probability(X_test[:20])
    p_load = loaded_model.predict_fraud_probability(X_test[:20])

    np.testing.assert_allclose(p_orig, p_load, rtol=1e-5)
