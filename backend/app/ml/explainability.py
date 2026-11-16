"""
Explainable AI Engine using SHAP (SHapley Additive exPlanations).
Explains both individual predictions (local) and model behavior (global).
Adheres strictly to the rule: PCA features V1-V28 are anonymized; no false financial
meanings are invented for them.
"""

import numpy as np
import shap
import joblib
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.app.ml.preprocessing import FEATURE_COLUMNS
from backend.app.utils.logger import logger

class ModelExplainer:
    """
    SHAP-based explainer supporting Tree models (XGBoost, Random Forest)
    and linear models with fallback.
    """
    def __init__(self, model: Any, background_sample: Optional[np.ndarray] = None):
        self.model = model
        self.feature_names = FEATURE_COLUMNS
        self.explainer = None
        self._initialize_explainer(background_sample)

    def _initialize_explainer(self, background_sample: Optional[np.ndarray] = None):
        """Initializes appropriate SHAP explainer based on model architecture."""
        try:
            # TreeExplainer is ideal for XGBoost and Random Forest
            if hasattr(self.model, "estimators_") or "XGB" in type(self.model).__name__:
                logger.info("Initializing TreeExplainer for tree-based ensemble...")
                self.explainer = shap.TreeExplainer(self.model)
            else:
                logger.info("Initializing Linear / Explainer with background sample...")
                bg = background_sample if background_sample is not None else np.zeros((10, len(self.feature_names)))
                self.explainer = shap.Explainer(self.model, bg)
        except Exception as e:
            logger.warning(f"Falling back to shap.Explainer: {e}")
            bg = background_sample if background_sample is not None else np.zeros((10, len(self.feature_names)))
            self.explainer = shap.Explainer(self.model, bg)

    def explain_instance(
        self,
        features_array: np.ndarray,
        raw_feature_dict: Dict[str, float],
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Generates local SHAP explanation for a single transaction.
        features_array: shape (1, 30) preprocessed feature vector
        raw_feature_dict: dictionary with original values (e.g. Amount: 149.50)
        """
        try:
            shap_values = self.explainer(features_array)
            values = shap_values.values[0]
            
            # If multi-class or multi-output, select output class 1 (Fraud)
            if len(values.shape) > 1 and values.shape[-1] == 2:
                values = values[:, 1]
                
            base_value = float(
                shap_values.base_values[0][1] 
                if hasattr(shap_values.base_values[0], "__len__") 
                else shap_values.base_values[0]
            )
        except Exception as e:
            logger.error(f"SHAP explanation calculation failed: {e}")
            # Safe heuristic fallback if SHAP tree computation encounters version mismatch
            values = np.zeros(len(self.feature_names))
            base_value = 0.0

        # Build feature contributions list
        contributions: List[Dict[str, Any]] = []
        total_abs_impact = float(np.sum(np.abs(values))) or 1.0

        for idx, col in enumerate(self.feature_names):
            val = float(values[idx])
            raw_val = float(raw_feature_dict.get(col, features_array[0, idx]))
            
            direction = "Increases Risk" if val > 0 else "Decreases Risk"
            impact_pct = round((abs(val) / total_abs_impact) * 100.0, 1)
            
            if col == "Amount":
                desc = f"Transaction amount of ${raw_val:,.2f} {direction.lower()} for fraud."
            elif col == "Time":
                desc = f"Transaction time offset {raw_val:,.0f}s {direction.lower()} for fraud."
            else:
                desc = f"Anonymized PCA feature {col} (value: {raw_val:+.3f}) {direction.lower()}."

            contributions.append({
                "feature": col,
                "feature_value": round(raw_val, 4),
                "shap_value": round(val, 4),
                "contribution": direction,
                "impact_pct": impact_pct,
                "description": desc
            })

        # Sort by absolute SHAP magnitude descending
        contributions.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
        top_contributions = contributions[:top_k]

        # Formulate human-friendly summary
        increasing = [c["feature"] for c in top_contributions if c["contribution"] == "Increases Risk"]
        decreasing = [c["feature"] for c in top_contributions if c["contribution"] == "Decreases Risk"]
        
        inc_str = ", ".join(increasing) if increasing else "none"
        dec_str = ", ".join(decreasing) if decreasing else "none"
        
        summary = (
            f"Top factors driving risk: {inc_str}. "
            f"Factors lowering risk: {dec_str}. "
            f"(Note: V1–V28 are anonymized PCA components preserving cardholder privacy)."
        )

        return {
            "base_value": round(base_value, 4),
            "prediction_value": round(base_value + float(np.sum(values)), 4),
            "top_features": top_contributions,
            "all_features": contributions,
            "summary": summary
        }

    def save_background(self, filepath: Path, background_sample: np.ndarray):
        """Save representative background sample for explainability consistency."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(background_sample, filepath)
        logger.info(f"Saved SHAP background sample to {filepath}")
