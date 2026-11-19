"""
FraudShield 3.0 Unified Engine Orchestrator (`FraudEngineV3`).
Orchestrates raw schema adaptation, PCI-DSS tokenization, streaming feature store
enrichment, LightGBM inference, and multi-tier decision policy routing.
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import threading
import pandas as pd
import joblib

from backend.app.v3.schemas.canonical import CanonicalTransaction
from backend.app.v3.adapters.iso8583_adapter import Iso8583Adapter
from backend.app.v3.adapters.ieee_cis_adapter import IeeeCisAdapter
from backend.app.v3.adapters.generic_json_adapter import GenericJsonAdapter
from backend.app.v3.services.token_service import KmsTokenService
from backend.app.v3.services.dual_engine_router import DualEngineRouter, EngineVersion
from backend.app.v3.feature_store.base import BaseFeatureStore
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.redis_store import RedisSlidingWindowStore
from backend.app.v3.feature_store.redis_connection import RedisManager, RedisConfig
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM
from backend.app.v3.ml.preprocessor import IeeeCisPreprocessor
from backend.app.v3.services.decision_engine import FraudDecisionEngine, DecisionResult, DecisionAction

logger = logging.getLogger(__name__)


@dataclass
class ModelBundle:
    model: FraudShieldLightGBM
    preprocessor: IeeeCisPreprocessor
    optimal_threshold: float
    manifest: Dict[str, Any]
    version: str


class FraudEngineV3:
    """
    Production-grade enterprise scoring orchestrator for FraudShield 3.0.
    """

    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        feature_store: Optional[BaseFeatureStore] = None,
        token_service: Optional[KmsTokenService] = None
    ):
        self.artifacts_dir = artifacts_dir or (Path(__file__).resolve().parent.parent.parent.parent / "artifacts" / "v3")
        self.token_service = token_service or KmsTokenService()

        # Initialize Adapters
        self.iso_adapter = Iso8583Adapter(token_service=self.token_service)
        self.ieee_adapter = IeeeCisAdapter(token_service=self.token_service)
        self.generic_adapter = GenericJsonAdapter(token_service=self.token_service)
        self.router = DualEngineRouter()

        # Initialize Feature Store & Resilient Connection
        self.redis_manager = RedisManager()
        self.in_memory_store = InMemorySlidingWindowStore()

        if feature_store:
            primary_store = feature_store
        elif self.redis_manager.ping():
            primary_store = RedisSlidingWindowStore(redis_client=self.redis_manager.get_client())
            logger.info("FraudEngineV3: Connected to primary Redis feature store.")
        else:
            primary_store = self.in_memory_store
            logger.info("FraudEngineV3: Redis unavailable. Initialized in-memory sliding window store.")

        self.pipeline = StreamingFeaturePipeline(
            feature_store=primary_store,
            fallback_store=self.in_memory_store
        )

        # Decision Engine
        self.decision_engine = FraudDecisionEngine()

        # Thread-safe atomic Model Bundle & references
        self._lock = threading.Lock()
        self._bundle: Optional[ModelBundle] = None
        self.model: Optional[FraudShieldLightGBM] = None
        self.preprocessor: Optional[IeeeCisPreprocessor] = None
        self.optimal_threshold: float = 0.700
        self.manifest: Dict[str, Any] = {}
        self.is_loaded: bool = False

        self.load_artifacts()

    def load_artifacts(self, version: Optional[str] = None) -> bool:
        """
        Loads trained LightGBM model, preprocessor, and threshold metadata.
        Uses thread-safe atomic bundle assignment to guarantee zero downtime
        and zero partially loaded states during concurrent scoring requests.
        """
        try:
            model_file = self.artifacts_dir / "lightgbm_fraudshield_v3.joblib"
            prep_file = self.artifacts_dir / "v3_preprocessor.joblib"
            thresh_file = self.artifacts_dir / "v3_optimal_threshold.json"
            manifest_file = self.artifacts_dir / "model_manifest.json"

            if not model_file.exists() or not prep_file.exists():
                logger.warning("FraudEngineV3: Artifacts not found at %s. Inference unavailable.", self.artifacts_dir)
                return False

            new_model = FraudShieldLightGBM.load(model_file)
            new_preprocessor = joblib.load(prep_file)
            new_threshold = 0.700
            new_manifest = {}

            if thresh_file.exists():
                with open(thresh_file, "r") as f:
                    t_data = json.load(f)
                    new_threshold = float(t_data.get("optimal_threshold", 0.700))

            if manifest_file.exists():
                with open(manifest_file, "r") as f:
                    new_manifest = json.load(f)

            ver = version or new_manifest.get("model_version", "3.0.0")

            new_bundle = ModelBundle(
                model=new_model,
                preprocessor=new_preprocessor,
                optimal_threshold=new_threshold,
                manifest=new_manifest,
                version=ver
            )

            # Atomic reference swap under lock
            with self._lock:
                self._bundle = new_bundle
                self.model = new_bundle.model
                self.preprocessor = new_bundle.preprocessor
                self.optimal_threshold = new_bundle.optimal_threshold
                self.manifest = new_bundle.manifest
                self.is_loaded = True

            logger.info(
                "FraudEngineV3: Successfully loaded model %s (optimal_threshold=%.3f, features=%d)",
                ver, new_threshold, len(new_model.feature_names_)
            )
            return True
        except Exception as exc:
            logger.error("FraudEngineV3: Failed to load ML artifacts: %s", exc, exc_info=True)
            if self._bundle is None:
                self.is_loaded = False
            return False

    def adapt_payload(self, raw_payload: Dict[str, Any]) -> CanonicalTransaction:
        """Routes payload to appropriate schema adapter and produces CanonicalTransaction."""
        # Detect payload flavor
        if "mti" in raw_payload or "raw_wire" in raw_payload:
            return self.iso_adapter.adapt(raw_payload)
        elif "TransactionAmt" in raw_payload or "card1" in raw_payload:
            return self.ieee_adapter.adapt(raw_payload)
        else:
            return self.generic_adapter.adapt(raw_payload)

    def _build_model_row(self, enriched_vector) -> pd.DataFrame:
        """Maps EnrichedFeatureVector attributes to raw IEEE-CIS schema for Preprocessor transformation."""
        # Map enriched feature vector fields into the format expected by IeeeCisPreprocessor
        row_dict = {
            "TransactionID": enriched_vector.transaction_id,
            "TransactionDT": int(enriched_vector.timestamp.timestamp()),
            "TransactionAmt": float(enriched_vector.amount),
            "ProductCD": "W",  # Standard e-commerce/retail default
            "card1": int(enriched_vector.card_bin[:5]) if enriched_vector.card_bin.isdigit() else 10000,
            "card2": 321.0,
            "card3": 150.0,
            "card4": enriched_vector.card_network.lower(),
            "card5": 226.0,
            "card6": enriched_vector.card_type.lower(),
            "addr1": 299.0,
            "addr2": 87.0,
            "dist1": enriched_vector.distance_km if enriched_vector.distance_km is not None else 10.0,
            "P_emaildomain": "gmail.com",
            "R_emaildomain": "gmail.com",
            "DeviceType": "desktop" if enriched_vector.channel == "ECOMMERCE" else "mobile",
            "DeviceInfo": "FraudShield POS Terminal v3",
            # Velocity counts mapped to C features
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
        }
        # Populate D and M features with defaults
        for i in range(1, 16):
            row_dict[f"D{i}"] = 1.0
        for i in range(1, 10):
            row_dict[f"M{i}"] = "T"
        # Populate V features
        for i in range(1, 340):
            row_dict[f"V{i}"] = 1.0

        return pd.DataFrame([row_dict])

    def score_transaction(self, canonical_tx: CanonicalTransaction) -> Dict[str, Any]:
        """
        Executes end-to-end scoring pipeline for a canonical transaction:
        1. Streaming feature enrichment & velocity accumulation
        2. Matrix transformation via preprocessor
        3. Monotonic LightGBM probability inference
        4. Multi-tier decision evaluation
        """
        start_t = time.perf_counter()

        # Step 1: Feature Store Enrichment
        enriched = self.pipeline.enrich(canonical_tx)

        # Atomic local bundle snapshot ensures thread safety under concurrent reload
        bundle = self._bundle
        if bundle is None or not self.is_loaded:
            prob = 0.50 if enriched.impossible_travel_flag else 0.05
            thresh = 0.700
            model_ver = "degraded_fallback"
            features_count = 0
        else:
            thresh = bundle.optimal_threshold
            model_ver = bundle.version
            features_count = len(bundle.model.feature_names_) if bundle.model else 0

            # Step 2 & 3: Fast-Path Feature Vectorization & Booster Inference
            if hasattr(bundle.preprocessor, "transform_single_enriched"):
                feature_arr = bundle.preprocessor.transform_single_enriched(enriched)
                if hasattr(bundle.model, "model_") and bundle.model.model_ and hasattr(bundle.model.model_, "booster_"):
                    prob = float(bundle.model.model_.booster_.predict(feature_arr)[0])
                else:
                    df_fast = pd.DataFrame(feature_arr, columns=bundle.preprocessor.feature_names_)
                    prob = float(bundle.model.predict_proba(df_fast)[0, 1])
            else:
                raw_row = self._build_model_row(enriched)
                trans_df = bundle.preprocessor.transform(raw_row)
                if "amount_ratio_baseline" in trans_df.columns:
                    trans_df["amount_ratio_baseline"] = enriched.card_amount_ratio_30d
                if "card_tx_count_historical" in trans_df.columns:
                    trans_df["card_tx_count_historical"] = enriched.card_tx_count_1h
                prob = float(bundle.model.predict_proba(trans_df)[0, 1])

        # Step 4: Decision Engine Policy Evaluation
        decision: DecisionResult = self.decision_engine.evaluate(
            fraud_probability=prob,
            features=enriched,
            optimal_threshold=thresh
        )

        elapsed_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

        return {
            "transaction_id": canonical_tx.transaction_id,
            "timestamp": canonical_tx.timestamp.isoformat(),
            "amount": canonical_tx.amount,
            "currency": canonical_tx.currency,
            "card_masked": f"{canonical_tx.card_bin}XXXXXX{canonical_tx.card_last4}",
            "is_fraud": decision.is_fraud_flagged,
            "fraud_probability": round(decision.fraud_probability, 4),
            "risk_score": decision.risk_score,
            "action": decision.action.value,
            "decision_reasons": decision.decision_reasons,
            "rule_triggers": decision.rule_triggers,
            "evidence": decision.evidence,
            "is_duplicate": enriched.is_duplicate,
            "is_degraded": getattr(enriched, "is_degraded", False),
            "features_imputed": getattr(enriched, "features_imputed", []),
            "features_used": features_count,
            "model_version": model_ver,
            "latency_ms": elapsed_ms,
            "feature_store_backend": "redis" if (self.redis_manager.circuit_breaker.state == "CLOSED" and self.redis_manager.get_client() is not None) else "in_memory_fallback"
        }

    def predict_raw(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convenience method adapting raw JSON/ISO/IEEE payload and scoring it."""
        canonical_tx = self.adapt_payload(raw_payload)
        return self.score_transaction(canonical_tx)

    def get_status(self) -> Dict[str, Any]:
        """Provides dual-engine telemetry, manifest metadata, and Redis health."""
        telemetry = self.redis_manager.get_telemetry()
        router_status = self.router.get_engine_status()
        return {
            "version": "3.0.0",
            "status": "OPERATIONAL" if self.is_loaded else "DEGRADED",
            "model_loaded": self.is_loaded,
            "model_manifest": self.manifest,
            "optimal_threshold": self.optimal_threshold,
            "feature_store": telemetry,
            "dual_engine_telemetry": router_status
        }


# Global singleton engine instance
engine_v3 = FraudEngineV3()
