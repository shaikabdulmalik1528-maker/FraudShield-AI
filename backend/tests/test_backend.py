"""
Comprehensive Backend Test Suite.
Tests health endpoints, input validation, authentication,
predict endpoints (single and batch), database operations,
alert workflow, SHAP explanation retrieval, and risk scoring.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.services.fraud_engine import fraud_engine
from backend.app.services.auth_service import get_password_hash
from backend.app.models.user import User
from backend.app.models.alert import FraudAlert
import backend.app.models.transaction
import backend.app.models.log
import backend.app.models.metric

# Use StaticPool with in-memory SQLite so all sessions share the exact same in-memory DB
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    fraud_engine.load_artifacts()
    
    # Create test analyst user
    db = TestingSessionLocal()
    user = User(
        username="testanalyst",
        email="test@fraudshield.ai",
        hashed_password=get_password_hash("TestPass123!"),
        role="admin",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    res = client.post("/api/v1/auth/login", data={"username": "testanalyst", "password": "TestPass123!"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_health_check(client):
    """Test health check returns 200 and operational status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data

def test_model_info_endpoint(client):
    """Test model info endpoint returns champion metadata."""
    response = client.get("/api/v1/model/info")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert "champion_model" in data
    assert "active_threshold" in data

def test_authentication_flow(client):
    """Test valid and invalid login attempts."""
    # Valid login
    res = client.post("/api/v1/auth/login", data={"username": "testanalyst", "password": "TestPass123!"})
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data

    # Invalid login
    bad_res = client.post("/api/v1/auth/login", data={"username": "testanalyst", "password": "WrongPassword"})
    assert bad_res.status_code == 401

def _submit_test_transaction(client):
    payload = {
        "Time": 406.0,
        "Amount": 149.62,
        "V1": -2.312, "V2": 1.951, "V3": -1.609, "V4": 3.997, "V5": -0.522,
        "V6": -1.426, "V7": -2.537, "V8": 1.391, "V9": -2.770, "V10": -2.772,
        "V11": 3.202, "V12": -2.899, "V13": -0.595, "V14": -4.289, "V15": 0.389,
        "V16": -1.140, "V17": -2.830, "V18": -0.016, "V19": 0.416, "V20": 0.126,
        "V21": 0.517, "V22": -0.035, "V23": -0.465, "V24": 0.320, "V25": 0.044,
        "V26": 0.177, "V27": 0.261, "V28": -0.143
    }
    response = client.post("/api/v1/predict", json=payload)
    return response

def test_predict_endpoint_valid(client):
    """Test real-time prediction with genuine PCA transaction features."""
    response = _submit_test_transaction(client)
    assert response.status_code == 200
    data = response.json()
    assert "transaction_id" in data
    assert "fraud_probability" in data
    assert "risk_score" in data
    assert data["risk_category"] in ["LOW", "MEDIUM", "HIGH"]
    assert data["prediction"] in ["LEGITIMATE", "SUSPICIOUS"]
    assert "explanation" in data
    assert "top_features" in data["explanation"]

def test_batch_predict_endpoint(client):

    """Test batch prediction endpoint with multiple transactions."""
    single_txn = {
        "Time": 100.0, "Amount": 50.0,
        "V1": 0.1, "V2": 0.2, "V3": -0.1, "V4": 0.4, "V5": -0.2,
        "V6": 0.1, "V7": 0.0, "V8": 0.0, "V9": 0.1, "V10": -0.1,
        "V11": 0.2, "V12": -0.1, "V13": 0.1, "V14": -0.2, "V15": 0.1,
        "V16": 0.0, "V17": -0.1, "V18": 0.0, "V19": 0.1, "V20": 0.0,
        "V21": 0.0, "V22": -0.1, "V23": 0.0, "V24": 0.1, "V25": 0.0,
        "V26": 0.1, "V27": 0.0, "V28": 0.0
    }
    payload = {"transactions": [single_txn, single_txn]}
    res = client.post("/api/v1/predict/batch", json=payload)
    assert res.status_code == 200
    batch_res = res.json()
    assert len(batch_res) == 2
    assert "transaction_id" in batch_res[0]

def test_predict_endpoint_invalid_input(client):
    """Test input validation: missing fields and negative amount."""
    bad_payload = {"Time": 100.0, "Amount": -50.0}
    response = client.post("/api/v1/predict", json=bad_payload)
    assert response.status_code == 422 # Pydantic Unprocessable Entity

def test_transactions_listing_and_filtering(client):
    """Test transaction history listing and pagination."""
    response = client.get("/api/v1/transactions?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

def test_explanation_endpoint_retrieval(client):
    """Test retrieving stored SHAP explanation by transaction_id."""
    # First submit a transaction
    sub_res = _submit_test_transaction(client)
    txn_id = sub_res.json()["transaction_id"]
    res = client.get(f"/api/v1/explanations/{txn_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["transaction_id"] == txn_id
    assert "explanation" in data
    assert "top_features" in data["explanation"]


def test_alert_lifecycle_workflow(client, auth_headers):
    """Test retrieving alerts and updating alert investigation status."""
    # Fetch alerts
    res = client.get("/api/v1/alerts")
    assert res.status_code == 200
    alerts = res.json()

    # Create an alert if empty
    if not alerts:
        db = TestingSessionLocal()
        al = FraudAlert(
            transaction_id="FS-TESTALERT1",
            risk_score=85.0,
            fraud_probability=0.92,
            status="PENDING",
            notes="Automated test alert"
        )
        db.add(al)
        db.commit()
        db.refresh(al)
        alert_id = al.id
        db.close()
    else:
        alert_id = alerts[0]["id"]

    # Update alert status (requires auth)
    update_res = client.patch(
        f"/api/v1/alerts/{alert_id}",
        json={"status": "INVESTIGATING", "notes": "Investigating with issuer bank"},
        headers=auth_headers
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["status"] == "INVESTIGATING"
    assert updated["acknowledged_by"] == "testanalyst"

def test_threshold_update_endpoint(client, auth_headers):
    """Test updating the active model decision threshold via admin endpoint."""
    res = client.post(
        "/api/v1/model/threshold",
        json={"threshold": 0.85},
        headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["new_threshold"] == 0.85

def test_analytics_endpoints(client):
    """Test overview and trend analytics."""
    overview_res = client.get("/api/v1/analytics/overview")
    assert overview_res.status_code == 200
    overview = overview_res.json()
    assert "total_transactions" in overview
    assert "fraud_rate_pct" in overview

    trends_res = client.get("/api/v1/analytics/fraud-trends")
    assert trends_res.status_code == 200
    assert isinstance(trends_res.json(), list)

    dist_res = client.get("/api/v1/analytics/risk-distribution")
    assert dist_res.status_code == 200
    assert len(dist_res.json()) == 3

    perf_res = client.get("/api/v1/analytics/model-performance")
    assert perf_res.status_code == 200
    perf = perf_res.json()
    assert "champion_model" in perf
