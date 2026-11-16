"""
Application configuration management using Pydantic Settings.
Reads environment variables with strong typing and default fallbacks.
"""

from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "FraudShield AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "fraudshield-super-secure-production-ready-jwt-secret-key-change-in-prod-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/fraudshield.db"
    
    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    # ML Artifact Paths
    ARTIFACTS_DIR: Path = BASE_DIR / "artifacts"
    SUPERVISED_MODEL_PATH: Path = BASE_DIR / "artifacts" / "best_fraud_model.joblib"
    PREPROCESSOR_PATH: Path = BASE_DIR / "artifacts" / "preprocessor.joblib"
    ANOMALY_MODEL_PATH: Path = BASE_DIR / "artifacts" / "isolation_forest.joblib"
    METRICS_PATH: Path = BASE_DIR / "artifacts" / "model_metrics.json"
    THRESHOLD_PATH: Path = BASE_DIR / "artifacts" / "optimal_threshold.json"
    SHAP_BACKGROUND_PATH: Path = BASE_DIR / "artifacts" / "shap_background.joblib"

    @field_validator(
        "SUPERVISED_MODEL_PATH",
        "PREPROCESSOR_PATH",
        "ANOMALY_MODEL_PATH",
        "METRICS_PATH",
        "THRESHOLD_PATH",
        "SHAP_BACKGROUND_PATH",
        mode="before"
    )
    @classmethod
    def resolve_artifact_paths(cls, v: Union[str, Path]) -> Path:
        p = Path(v)
        if not p.is_absolute():
            # Check relative to BASE_DIR first
            if (BASE_DIR / p).exists():
                return BASE_DIR / p
            elif (BASE_DIR / "artifacts" / p.name).exists():
                return BASE_DIR / "artifacts" / p.name
        return p


    # Risk Engine Default Parameters
    LOW_RISK_THRESHOLD: float = 30.0
    HIGH_RISK_THRESHOLD: float = 75.0
    FRAUD_WEIGHT: float = 0.75
    ANOMALY_WEIGHT: float = 0.25

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
