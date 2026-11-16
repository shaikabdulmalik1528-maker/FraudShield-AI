# FraudShield AI — Development Log & Engineering Journal

## Project Overview
- **Project Title:** FraudShield AI – Intelligent Credit Card Fraud Detection & Prevention System
- **Status:** **ALL 12 PHASES IMPLEMENTED, TRAINED, VERIFIED & RUNNING**
- **Runtime Environment:** Windows 11 (PowerShell), Python 3.12 (64-bit), Node.js v24.19.0, Vite + React + Tailwind CSS
- **Active Champion Model:** XGBoost Classifier (PR-AUC: 0.8052, F1-Score: 0.8488, Precision: 94.81%, Recall: 76.84%)
- **Active Backend Gateway:** Running on `http://127.0.0.1:8000`
- **Active Frontend Dashboard:** Running on `http://127.0.0.1:5173`

---

## 7-Day Implementation Schedule & Milestones

| Day | Focus Area | Status | Deliverables Achieved |
|---|---|---|---|
| **Day 1** | Project Setup, Architecture, Dataset Acquisition & EDA | ✅ Completed | Complete directory structure, Python 3.12 venv, dependencies, Kaggle dataset acquisition (`mlg-ulb/creditcardfraud`, 143.8MB), 10-step EDA pipeline, plots in `reports/figures/`, Jupyter notebook. |
| **Day 2** | Preprocessing, Feature Engineering & Imbalance Handling | ✅ Completed | Stratified 80/20 split strictly prior to scaling, RobustScaler pipeline for Amount and Time, train-only SMOTE resampler, data leakage prevention. |
| **Day 3** | ML Model Training, Comparison & Model Selection | ✅ Completed | Trained and compared Logistic Regression, Decision Tree, Random Forest, and XGBoost. Champion selected based on PR-AUC & F1 score. Saved artifacts via joblib. |
| **Day 4** | Hybrid Fraud Engine, Isolation Forest & SHAP Explainability | ✅ Completed | Integrated unsupervised Isolation Forest (150 trees, contamination 0.005), multi-signal risk aggregator (75% supervised + 25% anomaly), TreeSHAP explainer for local feature contributions and global importance. |
| **Day 5** | FastAPI Backend & Dual Database Architecture | ✅ Completed | 12 REST API endpoints, Pydantic v2 schemas, SQLAlchemy models with dual Postgres/SQLite support, JWT auth, prediction audit logging. |
| **Day 6** | React Frontend Dashboard & Data Visualizations | ✅ Completed | Dark navy fintech theme, KPI cards, Recharts area trend and risk distribution charts, Interactive Transaction Scorer with benchmark presets, alert management, model performance cards. |
| **Day 7** | System Integration, Verification Tests & Documentation | ✅ Completed | Pytest test suite (12 passed, 100%), Dockerfile, docker-compose.yml, OpenAPI docs, Model Card, architecture blueprint, portfolio README. |

---

## Completed Engineering Tasks

1. **Workspace Inspection & Environment Setup:**
   - Identified clean workspace.
   - Initialized Python 3.12 virtual environment (`venv`).
   - Installed core machine learning dependencies: `scikit-learn`, `xgboost`, `shap`, `imbalanced-learn`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `joblib`.
   - Installed backend framework: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `python-jose`, `bcrypt`.
   - Initialized frontend with React 18, Vite, Tailwind CSS, Lucide React, and Recharts.

2. **Dataset Acquisition & Exploratory Data Analysis (EDA):**
   - Downloaded genuine European Credit Card Fraud dataset from Kaggle via `kagglehub` directly into `data/raw/creditcard.csv` (150,828,752 bytes).
   - Executed 10-step automated EDA (`scripts/run_eda.py`):
     - Verified 284,807 rows, 31 columns, 0 missing values, 1,081 duplicates.
     - Confirmed 492 fraud vs 284,315 legit (0.1727% fraud rate).
     - Generated and saved visualizations to `reports/figures/`:
       - `class_imbalance.png`
       - `amount_distribution.png`
       - `correlation_heatmap.png`
       - `feature_distributions.png`
       - `eda_summary.json`
     - Created `notebooks/exploratory_analysis.ipynb`.

3. **Machine Learning Model Benchmark & Artifact Generation:**
   - Executed full comparative benchmark on 56,746 held-out test transactions (`python -m backend.app.ml.train data/raw/creditcard.csv`):
     - **Logistic Regression:** PR-AUC 0.6719, ROC-AUC 0.9657, F1 0.3990, Precision 26.25%, Recall 83.16%
     - **Decision Tree:** PR-AUC 0.4729, ROC-AUC 0.9148, F1 0.3056, Precision 18.83%, Recall 81.05%
     - **Random Forest:** PR-AUC 0.7859, ROC-AUC 0.9700, F1 0.8046, Precision 88.61%, Recall 73.68%
     - **XGBoost (Champion):** **PR-AUC 0.8052**, **ROC-AUC 0.9679**, **F1 0.8488**, **Precision 94.81%**, **Recall 76.84%** (Optimal Threshold: 0.895)
     - **Isolation Forest:** Fitted on 226,980 samples with contamination 0.005.
     - Serialized all artifacts into `backend/artifacts/`:
       - `best_fraud_model.joblib`
       - `preprocessor.joblib`
       - `isolation_forest.joblib`
       - `shap_background.joblib`
       - `optimal_threshold.json`
       - `model_metrics.json`

4. **Database Initialization & Seeding:**
   - Configured SQLAlchemy models: `User`, `Transaction`, `FraudAlert`, `PredictionLog`, `ModelMetric`.
   - Seeded default administrator account (`admin` / `AdminPass123!`).
   - Seeded 50 sample transactions drawn from the Kaggle dataset with pre-calculated risk scores and SHAP explanations.

5. **Pytest Verification Suite:**
   - Created `backend/tests/test_backend.py` and `backend/tests/test_ml.py`.
   - Ran `pytest backend/tests -v` $\rightarrow$ **12 passed in 7.00s (100% success rate)**.

6. **Frontend Dashboard:**
   - Built modern dark navy fintech interface with 6 complete pages:
     - `Dashboard`: Executive KPI cards, fraud trend chart, risk distribution pie, recent transaction feed.
     - `TransactionAnalysis`: Real-time transaction scorer with 3 benchmark presets, risk gauge, and SHAP horizontal bar chart.
     - `TransactionHistory`: Paginated transaction table with search and filtering by risk and verdict.
     - `FraudAlerts`: Alert investigation and resolution workflow.
     - `ModelPerformance`: Multi-algorithm comparison table, confusion matrix, top 10 feature importances.
     - `Settings`: Active pipeline specifications and runtime threshold slider.
     - `Login`: Analyst JWT authentication modal.
   - Verified production build via `npm run build` (built in 7.48s, 0 errors).

7. **Live Services Verification:**
   - FastAPI server verified live at `http://127.0.0.1:8000` (`GET /health` returned `200 OK`, `model_loaded: true`).
   - Live prediction endpoint verified via `POST /api/v1/predict` (returned `transaction_id`, `risk_score: 85.6`, `prediction: SUSPICIOUS`, `top_features` with SHAP impact values).
   - React frontend verified live at `http://127.0.0.1:5173` (`StatusCode 200 OK`).

---

## Error Log & Resolutions

1. **Error:** `ImportError: email-validator is not installed`
   - **Resolution:** Added `email-validator` to `backend/requirements.txt` and installed via pip.
2. **Error:** `ValueError: password cannot be longer than 72 bytes` caused by passlib bcrypt compatibility bug.
   - **Resolution:** Refactored `backend/app/utils/security.py` to use `bcrypt` directly (`bcrypt.hashpw` and `bcrypt.checkpw`), eliminating the passlib dependency issue while retaining high security.
3. **Error:** `sqlalchemy.exc.OperationalError: no such table: transactions` in test runner with SQLite in-memory database.
   - **Resolution:** Configured `poolclass=StaticPool` in test engine to ensure all test client sessions share the same in-memory connection and tables.
