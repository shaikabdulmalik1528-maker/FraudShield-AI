# FraudShield AI — REST API Documentation

Base URL: `http://localhost:8000`  
Interactive Swagger UI: `http://localhost:8000/docs`  
Interactive ReDoc: `http://localhost:8000/redoc`

---

## 1. System Health

### `GET /health`
Returns runtime operational status and ML model availability.

**Response:**
```json
{
  "status": "healthy",
  "service": "FraudShield AI",
  "environment": "development",
  "model_loaded": true,
  "timestamp": "2026-11-16T08:16:07.350870+00:00"
}
```

---

## 2. Authentication

### `POST /api/v1/auth/login`
Exchanges analyst username and password for a JWT Bearer access token.
- Content-Type: `application/x-www-form-urlencoded`
- Fields: `username`, `password`

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### `GET /api/v1/auth/me`
Retrieves authenticated user profile. Requires `Authorization: Bearer <token>`.

---

## 3. Real-Time Inference

### `POST /api/v1/predict`
Evaluates a single transaction through the hybrid ML engine and generates SHAP attribution.

**Request Payload:**
```json
{
  "Time": 406.0,
  "Amount": 489.20,
  "V1": -2.312, "V2": 1.951, "V3": -1.609, "V4": 3.997, "V5": -0.522,
  "V6": -1.426, "V7": -2.537, "V8": 1.391, "V9": -2.770, "V10": -2.772,
  "V11": 3.202, "V12": -2.899, "V13": -0.595, "V14": -4.289, "V15": 0.389,
  "V16": -1.140, "V17": -2.830, "V18": -0.016, "V19": 0.416, "V20": 0.126,
  "V21": 0.517, "V22": -0.035, "V23": -0.465, "V24": 0.320, "V25": 0.044,
  "V26": 0.177, "V27": 0.261, "V28": -0.143,
  "notes": "E-commerce checkout"
}
```

**Response (HTTP 200 OK):**
```json
{
  "transaction_id": "FS-2EFC5654E7",
  "timestamp": "2026-11-16T08:16:30.000048Z",
  "amount": 489.2,
  "fraud_probability": 0.9994,
  "fraud_probability_pct": 99.94,
  "is_anomaly": false,
  "anomaly_score": 0.4243,
  "risk_score": 85.6,
  "risk_category": "HIGH",
  "prediction": "SUSPICIOUS",
  "model_version": "1.0.0",
  "explanation": {
    "base_value": -0.0324,
    "prediction_value": 7.4091,
    "top_features": [
      {
        "feature": "V14",
        "feature_value": -4.289,
        "shap_value": 4.7557,
        "contribution": "Increases Risk",
        "impact_pct": 38.5,
        "description": "Anonymized PCA feature V14 (value: -4.289) increases risk."
      }
    ],
    "summary": "Top factors driving risk: V14, V12, V10, V4. Factors lowering risk: Time."
  }
}
```

---

## 4. Transaction History

### `GET /api/v1/transactions`
Retrieves paginated audit history with multi-attribute filtering.
- Query Parameters:
  - `page` (integer, default 1)
  - `page_size` (integer, default 15)
  - `risk_category` (string, optional: `LOW`, `MEDIUM`, `HIGH`)
  - `prediction` (string, optional: `LEGITIMATE`, `SUSPICIOUS`)
  - `search` (string, optional search on `transaction_id`)

### `GET /api/v1/transactions/{transaction_id}`
Returns exact parameters, predictions, and stored SHAP waterfall for a single transaction.

---

## 5. Fraud Incident Alerts

### `GET /api/v1/alerts`
Returns flagged incidents requiring analyst acknowledgment. Filterable by `status`.

### `PATCH /api/v1/alerts/{alert_id}`
Updates alert resolution. Requires authentication.
- Request Body:
```json
{
  "status": "RESOLVED",
  "notes": "Cardholder confirmed transaction was unauthorized."
}
```

---

## 6. Executive Analytics

### `GET /api/v1/analytics/overview`
Returns high-level KPI cards (Total transactions, fraud count, fraud rate, average risk, USD volumes).

### `GET /api/v1/analytics/fraud-trends`
Returns time-series transaction and fraud counts for Recharts area charts.

### `GET /api/v1/analytics/risk-distribution`
Returns categorized count and percentage breakdown across LOW, MEDIUM, and HIGH risk bands.

### `GET /api/v1/analytics/model-performance`
Returns authentic benchmark comparison across all tested algorithms (PR-AUC, F1, Precision, Recall, Confusion Matrix).
