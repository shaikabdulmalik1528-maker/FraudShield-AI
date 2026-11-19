"""
FraudShield 3.0 API Routes Package.
"""

from backend.app.v3.routes.predict import router as v3_predict_router

__all__ = ["v3_predict_router"]
