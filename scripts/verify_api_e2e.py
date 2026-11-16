"""
FraudShield AI - End-to-End Live API Verification Suite.
Directly exercises every API endpoint and workflow against the live running server.
"""

import sys
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def run_e2e_verification():
    print("=" * 70)
    print("RUNNING LIVE END-TO-END API AUDIT & VERIFICATION")
    print(f"Target Gateway: {BASE_URL}")
    print("=" * 70)
    
    session = requests.Session()
    tests_passed = 0
    total_tests = 0

    def assert_test(name, condition, details=""):
        nonlocal tests_passed, total_tests
        total_tests += 1
        if condition:
            tests_passed += 1
            print(f" [PASS] {name} {details}")
        else:
            print(f" [FAIL] {name} {details}")
            sys.exit(1)

    # 1. Health Endpoint
    res = session.get(f"{BASE_URL}/health")
    assert_test("GET /health", res.status_code == 200 and res.json()["status"] == "healthy")

    # 2. Model Info
    res = session.get(f"{BASE_URL}/api/v1/model/info")
    info = res.json()
    assert_test("GET /api/v1/model/info", res.status_code == 200 and info["status"] == "active", f"(Champion: {info.get('champion_model')})")

    # 3. Authentication: Login
    login_data = {"username": "admin", "password": "AdminPass123!"}
    res = session.post(f"{BASE_URL}/api/v1/auth/login", data=login_data)
    assert_test("POST /api/v1/auth/login", res.status_code == 200 and "access_token" in res.json())
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Authentication: Profile
    res = session.get(f"{BASE_URL}/api/v1/auth/me", headers=headers)
    assert_test("GET /api/v1/auth/me", res.status_code == 200 and res.json()["username"] == "admin")

    # 5. Predict: Legitimate Transaction
    legit_payload = {
        "Time": 12050.0, "Amount": 35.50,
        "V1": 0.124, "V2": -0.052, "V3": 0.982, "V4": 0.412, "V5": -0.210,
        "V6": 0.150, "V7": -0.120, "V8": 0.080, "V9": 0.320, "V10": -0.110,
        "V11": -0.450, "V12": 0.230, "V13": 0.650, "V14": -0.180, "V15": 0.890,
        "V16": 0.120, "V17": -0.050, "V18": 0.020, "V19": -0.150, "V20": 0.040,
        "V21": -0.080, "V22": -0.120, "V23": 0.050, "V24": 0.180, "V25": -0.210,
        "V26": 0.110, "V27": 0.020, "V28": 0.010,
        "notes": "E2E verification legitimate checkout"
    }
    res = session.post(f"{BASE_URL}/api/v1/predict", json=legit_payload)
    pred_legit = res.json()
    assert_test("POST /api/v1/predict (Legit)", res.status_code == 200 and pred_legit["prediction"] == "LEGITIMATE", f"(Risk: {pred_legit['risk_score']})")

    # 6. Predict: Fraudulent Transaction with SHAP
    fraud_payload = {
        "Time": 406.0, "Amount": 489.20,
        "V1": -2.312, "V2": 1.951, "V3": -1.609, "V4": 3.997, "V5": -0.522,
        "V6": -1.426, "V7": -2.537, "V8": 1.391, "V9": -2.770, "V10": -2.772,
        "V11": 3.202, "V12": -2.899, "V13": -0.595, "V14": -4.289, "V15": 0.389,
        "V16": -1.140, "V17": -2.830, "V18": -0.016, "V19": 0.416, "V20": 0.126,
        "V21": 0.517, "V22": -0.035, "V23": -0.465, "V24": 0.320, "V25": 0.044,
        "V26": 0.177, "V27": 0.261, "V28": -0.143,
        "notes": "E2E verification high-risk fraud test"
    }
    res = session.post(f"{BASE_URL}/api/v1/predict", json=fraud_payload)
    pred_fraud = res.json()
    fraud_txn_id = pred_fraud["transaction_id"]
    has_shap = "explanation" in pred_fraud and len(pred_fraud["explanation"]["top_features"]) > 0
    assert_test("POST /api/v1/predict (Fraud)", res.status_code == 200 and pred_fraud["prediction"] == "SUSPICIOUS" and has_shap, f"(ID: {fraud_txn_id}, Risk: {pred_fraud['risk_score']})")

    # 7. Predict Batch
    batch_payload = {"transactions": [legit_payload, fraud_payload]}
    res = session.post(f"{BASE_URL}/api/v1/predict/batch", json=batch_payload)
    assert_test("POST /api/v1/predict/batch", res.status_code == 200 and len(res.json()) == 2)

    # 8. Transactions Listing & Search
    res = session.get(f"{BASE_URL}/api/v1/transactions?page=1&page_size=5")
    assert_test("GET /api/v1/transactions", res.status_code == 200 and len(res.json()["items"]) > 0)

    # 9. Single Transaction by ID
    res = session.get(f"{BASE_URL}/api/v1/transactions/{fraud_txn_id}")
    assert_test(f"GET /api/v1/transactions/{fraud_txn_id}", res.status_code == 200 and res.json()["transaction_id"] == fraud_txn_id)

    # 10. SHAP Explanation Lookup by Transaction ID
    res = session.get(f"{BASE_URL}/api/v1/explanations/{fraud_txn_id}")
    assert_test(f"GET /api/v1/explanations/{fraud_txn_id}", res.status_code == 200 and "explanation" in res.json())

    # 11. Alerts Listing
    res = session.get(f"{BASE_URL}/api/v1/alerts")
    alerts = res.json()
    assert_test("GET /api/v1/alerts", res.status_code == 200 and isinstance(alerts, list))

    # 12. Alert Acknowledgment & Status Update
    if alerts:
        target_alert = alerts[0]
        update_payload = {"status": "INVESTIGATING", "notes": "Audited via automated E2E test"}
        res = session.patch(f"{BASE_URL}/api/v1/alerts/{target_alert['id']}", json=update_payload, headers=headers)
        assert_test(f"PATCH /api/v1/alerts/{target_alert['id']}", res.status_code == 200 and res.json()["status"] == "INVESTIGATING")

    # 13. Analytics: Overview
    res = session.get(f"{BASE_URL}/api/v1/analytics/overview")
    overview = res.json()
    assert_test("GET /api/v1/analytics/overview", res.status_code == 200 and overview["total_transactions"] > 0)

    # 14. Analytics: Fraud Trends
    res = session.get(f"{BASE_URL}/api/v1/analytics/fraud-trends")
    assert_test("GET /api/v1/analytics/fraud-trends", res.status_code == 200 and isinstance(res.json(), list))

    # 15. Analytics: Risk Distribution
    res = session.get(f"{BASE_URL}/api/v1/analytics/risk-distribution")
    assert_test("GET /api/v1/analytics/risk-distribution", res.status_code == 200 and len(res.json()) == 3)

    # 16. Analytics: Model Performance Benchmark
    res = session.get(f"{BASE_URL}/api/v1/analytics/model-performance")
    perf = res.json()
    assert_test("GET /api/v1/analytics/model-performance", res.status_code == 200 and "champion_metrics" in perf)

    # 17. Runtime Threshold Adjustment (Admin only)
    res = session.post(f"{BASE_URL}/api/v1/model/threshold", json={"threshold": 0.895}, headers=headers)
    assert_test("POST /api/v1/model/threshold", res.status_code == 200 and res.json()["new_threshold"] == 0.895)

    print("=" * 70)
    print(f"VERIFICATION SUMMARY: {tests_passed} / {total_tests} LIVE API ENDPOINTS PASSED (100% SUCCESS)")
    print("=" * 70)

if __name__ == "__main__":
    run_e2e_verification()
