"""
FraudShield AI - FastAPI Application Entry Point.
Production-grade REST API for intelligent credit card fraud detection,
risk calculation, anomaly detection, and SHAP explainability.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from backend.app.config import settings
from backend.app.database import init_db
from backend.app.services.fraud_engine import fraud_engine
from backend.app.utils.logger import logger

# Import Routers
from backend.app.routes.health import router as health_router
from backend.app.routes.auth import router as auth_router
from backend.app.routes.predict import router as predict_router
from backend.app.routes.transactions import router as transactions_router
from backend.app.routes.alerts import router as alerts_router
from backend.app.routes.analytics import router as analytics_router
from backend.app.routes.model import router as model_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for application startup and shutdown."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode...")
    # Initialize database tables
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)
    
    # Load ML artifacts into memory
    loaded = fraud_engine.load_artifacts()
    if loaded:
        logger.info("[SUCCESS] Hybrid ML models and SHAP explainer ready for inference.")
    else:
        logger.warning("[WARNING] ML artifacts not loaded yet. Predictions will require trained artifacts.")

    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Credit Card Fraud Detection, Anomaly Scoring, and Explainable AI Platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Request Timing & Audit Middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact system administrator."}
    )

# Include Routers
app.include_router(health_router)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(predict_router, prefix=settings.API_V1_STR)
app.include_router(transactions_router, prefix=settings.API_V1_STR)
app.include_router(alerts_router, prefix=settings.API_V1_STR)
app.include_router(analytics_router, prefix=settings.API_V1_STR)
app.include_router(model_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "documentation": "/docs",
        "status": "operational"
    }
