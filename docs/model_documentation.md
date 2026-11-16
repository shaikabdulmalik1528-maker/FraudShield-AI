# FraudShield AI — Machine Learning Model Documentation & Benchmark Card

## 1. Problem Formulation & Objective
Credit card fraud detection is characterized by **extreme class imbalance** (0.17% fraud rate) and high asymmetric costs. A false negative (missed fraud) leads to direct financial loss and regulatory liability, while a false positive (declining a legitimate cardholder) introduces customer friction.

The primary objective is to maximize **PR-AUC (Precision-Recall Area Under Curve)** and **F1-Score** while maintaining strict sub-10ms inference latency and explainability.

---

## 2. Dataset Characteristics
- **Source:** European Cardholders Credit Card Fraud Detection Dataset (ULB ML Group / Kaggle)
- **Total Transactions:** 284,807
- **Fraudulent Transactions:** 492 (0.1727%)
- **Legitimate Transactions:** 284,315 (99.8273%)
- **Features:**
  - `Time`: Elapsed seconds since first recorded transaction.
  - `Amount`: Transaction monetary value (highly skewed with extreme outliers).
  - `V1` to `V28`: Principal Component Analysis (PCA) orthogonal projections for privacy preservation.
  - `Class`: 1 for fraudulent, 0 for legitimate.

---

## 3. Data Preprocessing & Leakage Prevention
To guarantee zero distribution and target leakage:
1. **Stratified Split:** An 80/20 stratified split was computed strictly prior to any transformation.
   - Train Split: 226,980 samples (378 fraud, 226,602 legit)
   - Test Split: 56,746 samples (95 fraud, 56,651 legit)
2. **RobustScaler:** `Amount` and `Time` are scaled using median and Interquartile Range (IQR) through `sklearn.preprocessing.RobustScaler` fitted solely on training data.
3. **Train-Only SMOTE:** Synthetic oversampling is never applied to the evaluation split.
4. **Imbalance Cost Weighting:** `scale_pos_weight = 599.48` was calculated and applied to penalize false negatives proportionally.

---

## 4. Empirical Algorithm Benchmark Results

Evaluated on the held-out test split (56,746 transactions):

| Model Algorithm | PR-AUC | ROC-AUC | Precision | Recall | F1-Score | Optimal Threshold | Training Time |
|---|---|---|---|---|---|---|---|
| **XGBoost (Champion)** | **0.8052** | **0.9679** | **94.81%** | **76.84%** | **0.8488** | **0.895** | 2.1s |
| Random Forest | 0.7859 | 0.9700 | 88.61% | 73.68% | 0.8046 | 0.669 | 18.2s |
| Logistic Regression | 0.6719 | 0.9657 | 26.25% | 83.16% | 0.3990 | 0.900 | 2.0s |
| Decision Tree | 0.4729 | 0.9148 | 18.83% | 81.05% | 0.3056 | 0.900 | 6.8s |

---

## 5. Champion Confusion Matrix Analysis (XGBoost @ Threshold 0.895)
- **True Positives (TP):** 73 frauds caught
- **False Negatives (FN):** 22 frauds missed
- **True Negatives (TN):** 56,647 legitimate transactions cleared
- **False Positives (FP):** 4 false alarms out of 56,651 legitimate transactions

---

## 6. Unsupervised Anomaly Detection (Isolation Forest)
- **Contamination Parameter:** 0.005 (0.5%)
- **Estimators:** 150 Isolation Trees
- **Raw Decision Function Range:** `[-0.1528, 0.2651]`
- **Normalization:** Inverted min-max scaling mapping raw isolation depth to a $[0.0, 1.0]$ anomaly risk probability.
