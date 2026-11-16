"""
Data Preprocessing and Feature Engineering Pipeline.
Strictly prevents data leakage by fitting transformations solely on the training split.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any, Optional
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE
from backend.app.utils.logger import logger

# Feature column order as defined in the Kaggle Credit Card dataset
FEATURE_COLUMNS = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
TARGET_COLUMN = "Class"

class FraudDataPreprocessor(BaseEstimator, TransformerMixin):
    """
    Custom transformer that scales 'Amount' and 'Time' using RobustScaler,
    while passing through PCA features (V1-V28) which are already scaled.
    """
    def __init__(self):
        self.amount_scaler = RobustScaler()
        self.time_scaler = RobustScaler()
        self.feature_names = FEATURE_COLUMNS
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, y=None):
        df = pd.DataFrame(X, columns=self.feature_names) if not isinstance(X, pd.DataFrame) else X
        
        # Fit scalers only on training data
        self.amount_scaler.fit(df[["Amount"]])
        self.time_scaler.fit(df[["Time"]])
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Preprocessor must be fitted before transforming data.")
            
        df = pd.DataFrame(X, columns=self.feature_names).copy() if not isinstance(X, pd.DataFrame) else X.copy()
        
        # Apply scaling
        scaled_amount = self.amount_scaler.transform(df[["Amount"]])
        scaled_time = self.time_scaler.transform(df[["Time"]])
        
        # Assemble feature array in strictly identical order: Time, V1..V28, Amount
        pca_cols = [f"V{i}" for i in range(1, 29)]
        pca_vals = df[pca_cols].to_numpy()
        
        transformed = np.column_stack([scaled_time, pca_vals, scaled_amount])
        return transformed

    def transform_single(self, transaction_dict: Dict[str, float]) -> np.ndarray:
        """Helper to transform a single transaction dictionary for real-time inference."""
        row_df = pd.DataFrame([transaction_dict])[self.feature_names]
        return self.transform(row_df)

def load_and_clean_data(file_path: str) -> pd.DataFrame:
    """
    Loads dataset, logs shape, checks missing values and duplicate records.
    """
    logger.info(f"Loading dataset from: {file_path}")
    df = pd.read_csv(file_path)
    logger.info(f"Raw dataset shape: {df.shape}")
    
    # Missing values check
    missing = df.isnull().sum().sum()
    if missing > 0:
        logger.warning(f"Found {missing} missing values; imputing with median.")
        df = df.fillna(df.median())
    else:
        logger.info("Dataset has zero missing values.")
        
    # Duplicate check
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        logger.info(f"Dataset contains {duplicates} duplicates. Keeping unique rows for training stability.")
        df = df.drop_duplicates()
        logger.info(f"Deduplicated dataset shape: {df.shape}")
        
    return df

def prepare_stratified_split(
    df: pd.DataFrame,
    test_size: float = 0.15,
    val_size: float = 0.15,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """
    Performs 3-way stratified train/val/test split strictly BEFORE any SMOTE or scaling.
    This guarantees zero data leakage:
    - Train split: Used solely for model parameter learning and scaler fitting.
    - Validation split: Used solely for hyperparameter comparison and threshold tuning.
    - Test split: Pure held-out benchmark data evaluated at the validation-selected threshold.
    """
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN].astype(int)
    
    # First split off the final held-out test set
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y
    )
    
    # From remaining, split off the validation set
    val_ratio = val_size / (1.0 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp,
        test_size=val_ratio,
        random_state=random_state,
        stratify=y_temp
    )
    
    logger.info(f"Training split: {X_train.shape[0]} samples (Fraud: {y_train.sum()}, Legit: {(y_train == 0).sum()})")
    logger.info(f"Validation split: {X_val.shape[0]} samples (Fraud: {y_val.sum()}, Legit: {(y_val == 0).sum()})")
    logger.info(f"Test split: {X_test.shape[0]} samples (Fraud: {y_test.sum()}, Legit: {(y_test == 0).sum()})")
    return X_train, X_val, X_test, y_train, y_val, y_test


def apply_smote_resampling(
    X_train: np.ndarray,
    y_train: np.ndarray,
    sampling_strategy: float = 0.1,  # 10% fraud ratio in train to avoid over-blurring boundary
    random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Applies Synthetic Minority Over-sampling Technique (SMOTE) strictly to the training split.
    NEVER oversample the test set!
    """
    logger.info("Applying SMOTE oversampling to training set...")
    smote = SMOTE(sampling_strategy=sampling_strategy, random_state=random_state)
    X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
    logger.info(f"Resampled training set: {X_resampled.shape[0]} samples (Fraud: {y_resampled.sum()})")
    return X_resampled, y_resampled
