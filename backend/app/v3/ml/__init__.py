"""
FraudShield 3.0 Machine Learning Package.
Provides LightGBM model architecture, leakage-free temporal preprocessors,
evaluation suites, and reproducible training pipelines.
"""

from backend.app.v3.ml.data_loader import load_ieee_cis_dataset, generate_ieee_cis_benchmark
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split, IeeeCisPreprocessor
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM, DEFAULT_LGBM_PARAMS
from backend.app.v3.ml.evaluation import (
    compute_classification_metrics,
    find_optimal_threshold_v3,
    benchmark_inference_latency,
    compare_models
)
from backend.app.v3.ml.train_pipeline import run_training_pipeline

__all__ = [
    "load_ieee_cis_dataset",
    "generate_ieee_cis_benchmark",
    "temporal_train_val_test_split",
    "IeeeCisPreprocessor",
    "FraudShieldLightGBM",
    "DEFAULT_LGBM_PARAMS",
    "compute_classification_metrics",
    "find_optimal_threshold_v3",
    "benchmark_inference_latency",
    "compare_models",
    "run_training_pipeline"
]
