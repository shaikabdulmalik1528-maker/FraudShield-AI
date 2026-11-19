"""
FraudShield 3.0 LightGBM Model Architecture.
Implements supervised gradient-boosted tree classifier with native categorical splits,
monotonic risk constraints, class imbalance handling, and low-latency inference.
"""

import logging
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple
import numpy as np
import pandas as pd
import lightgbm as lgb
import joblib

logger = logging.getLogger(__name__)

DEFAULT_LGBM_PARAMS = {
    "objective": "binary",
    "metric": ["auc", "binary_logloss"],
    "boosting_type": "gbdt",
    "learning_rate": 0.03,
    "num_leaves": 63,
    "max_depth": 8,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "scale_pos_weight": 5.0,  # Compensates for ~3.5% fraud class imbalance
    "n_estimators": 500,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1
}


class FraudShieldLightGBM:
    """
    LightGBM model wrapper for enterprise fraud classification.
    Supports native integer categoricals, monotonic domain constraints,
    early stopping, and sub-3.5ms single-row inference.
    """

    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
        enforce_monotonic: bool = True
    ):
        self.params = dict(DEFAULT_LGBM_PARAMS)
        if params:
            self.params.update(params)
        self.enforce_monotonic = enforce_monotonic
        self.model_: Optional[lgb.LGBMClassifier] = None
        self.feature_names_: List[str] = []
        self.categorical_features_: List[str] = []
        self.best_iteration_: Optional[int] = None
        self.monotone_constraints_: Optional[List[int]] = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        eval_set: Optional[List[Tuple[pd.DataFrame, pd.Series]]] = None,
        categorical_feature: Optional[List[str]] = None,
        early_stopping_rounds: int = 50
    ):
        """Fits LightGBM classifier with early stopping and optional monotonic constraints."""
        self.feature_names_ = list(X_train.columns)
        self.categorical_features_ = categorical_feature or []

        # Monotonic Constraints: ensure higher risk velocity can never decrease fraud probability
        if self.enforce_monotonic:
            monotone_cols = {"amount_ratio_baseline", "card_tx_count_historical", "C1", "C2", "C3"}
            self.monotone_constraints_ = [
                1 if col in monotone_cols else 0 for col in self.feature_names_
            ]
            self.params["monotone_constraints"] = self.monotone_constraints_
            logger.info("Enforcing monotonic constraints on %d features", sum(self.monotone_constraints_))
        else:
            self.params.pop("monotone_constraints", None)

        logger.info(
            "Fitting FraudShieldLightGBM on N=%d samples (num_leaves=%d, lr=%.3f, monotonic=%s)...",
            len(X_train), self.params["num_leaves"], self.params["learning_rate"], self.enforce_monotonic
        )

        callbacks = [lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=False)]
        callbacks.append(lgb.log_evaluation(period=100))

        # Explicitly configure categorical columns for native integer splitting
        cat_cols = [c for c in self.categorical_features_ if c in X_train.columns]

        self.model_ = lgb.LGBMClassifier(**self.params)
        self.model_.fit(
            X=X_train,
            y=y_train,
            eval_set=eval_set,
            categorical_feature=cat_cols if cat_cols else "auto",
            callbacks=callbacks
        )

        self.best_iteration_ = getattr(self.model_, "best_iteration_", self.params["n_estimators"])
        logger.info("LightGBM fitting complete. Best iteration: %s", self.best_iteration_)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Returns predicted probability array [P(legitimate), P(fraud)]."""
        if self.model_ is None:
            raise RuntimeError("Model is not fitted. Call fit() or load() first.")
        return self.model_.predict_proba(X)

    def predict_fraud_probability(self, X: pd.DataFrame) -> np.ndarray:
        """Convenience method returning 1D array of fraud probabilities P(fraud | X)."""
        return self.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame, threshold: float = 0.50) -> np.ndarray:
        """Predicts binary fraud class against calibrated decision threshold."""
        p_fraud = self.predict_fraud_probability(X)
        return (p_fraud >= threshold).astype(np.int32)

    def predict_single(self, row_series: Union[pd.Series, Dict[str, Any]]) -> float:
        """
        Optimized single-row prediction for sub-3.5ms streaming inference SLA.
        """
        if isinstance(row_series, pd.DataFrame):
            row_df = row_series
        elif isinstance(row_series, dict):
            row_df = pd.DataFrame([row_series], columns=self.feature_names_)
        elif isinstance(row_series, pd.Series):
            row_df = pd.DataFrame([row_series.values], columns=self.feature_names_)
        else:
            row_df = pd.DataFrame(np.atleast_2d(row_series), columns=self.feature_names_)
        return float(self.predict_fraud_probability(row_df)[0])

    @property
    def feature_importances_(self) -> pd.DataFrame:
        """Returns feature importance ranking dataframe (gain & split)."""
        if self.model_ is None:
            raise RuntimeError("Model is not fitted.")
        return pd.DataFrame({
            "feature": self.feature_names_,
            "importance_split": self.model_.booster_.feature_importance(importance_type="split"),
            "importance_gain": self.model_.booster_.feature_importance(importance_type="gain")
        }).sort_values(by="importance_gain", ascending=False).reset_index(drop=True)

    def save(self, filepath_base: Union[str, Path]):
        """Saves both native LightGBM text model and joblib bundle."""
        base = Path(filepath_base)
        base.parent.mkdir(parents=True, exist_ok=True)

        joblib_path = base.with_suffix(".joblib")
        txt_path = base.with_suffix(".txt")

        # Save native booster text format (guarantees cross-platform portability)
        self.model_.booster_.save_model(str(txt_path))

        # Save wrapper bundle
        bundle = {
            "params": self.params,
            "feature_names": self.feature_names_,
            "categorical_features": self.categorical_features_,
            "best_iteration": self.best_iteration_,
            "enforce_monotonic": self.enforce_monotonic,
            "monotone_constraints": self.monotone_constraints_
        }
        joblib.dump((self.model_, bundle), joblib_path)
        logger.info("Saved LightGBM model to %s and %s", joblib_path, txt_path)

    @classmethod
    def load(cls, filepath_joblib: Union[str, Path]) -> "FraudShieldLightGBM":
        """Loads trained model bundle from joblib artifact."""
        model_inst, bundle = joblib.load(filepath_joblib)
        instance = cls(params=bundle["params"], enforce_monotonic=bundle["enforce_monotonic"])
        instance.model_ = model_inst
        instance.feature_names_ = bundle["feature_names"]
        instance.categorical_features_ = bundle["categorical_features"]
        instance.best_iteration_ = bundle["best_iteration"]
        instance.monotone_constraints_ = bundle.get("monotone_constraints")
        return instance
