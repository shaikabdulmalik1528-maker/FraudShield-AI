import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
from scipy.special import logit
from sklearn.model_selection import StratifiedKFold
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR))

from backend.app.ml.preprocessing import load_and_clean_data, prepare_stratified_split
from backend.app.ml.anomaly import AnomalyDetector

df = load_and_clean_data(str(BASE_DIR / "data" / "raw" / "creditcard.csv"))
X_train, X_val, X_test, y_train, y_val, y_test = prepare_stratified_split(df)
del X_test, y_test

log_clf = joblib.load(BASE_DIR / "experiments" / "milestone_2c" / "scratch" / "final_logistic_calibrator.joblib")

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
y_train_arr = y_train.values

fold_metrics = []
for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train_arr), 1):
    prep = joblib.load(BASE_DIR / "experiments" / "milestone_2c" / "scratch" / f"fold_{fold}_preprocessor.joblib")
    xgb = joblib.load(BASE_DIR / "experiments" / "milestone_2c" / "scratch" / f"fold_{fold}_xgboost.joblib")
    iforest = AnomalyDetector.load(BASE_DIR / "experiments" / "milestone_2c" / "scratch" / f"fold_{fold}_isolation_forest.joblib")
    
    X_f_val = prep.transform(X_train.iloc[val_idx])
    y_f_val = y_train_arr[val_idx]
    
    probs = xgb.predict_proba(X_f_val)[:, 1]
    _, anom_scores = iforest.predict_anomaly(X_f_val)
    
    x_cal = np.column_stack([logit(np.clip(probs, 1e-6, 1.0 - 1e-6)), anom_scores])
    cal_p = log_clf.predict_proba(x_cal)[:, 1]
    
    preds = ((cal_p * 100.0) >= 50.0).astype(int)
    
    tn, fp, fn, tp = confusion_matrix(y_f_val, preds).ravel()
    rec = recall_score(y_f_val, preds)
    prec = precision_score(y_f_val, preds)
    f1 = f1_score(y_f_val, preds)
    fold_metrics.append({
        "fold": fold,
        "total_fraud": int(np.sum(y_f_val)),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "recall": float(round(rec, 4)),
        "precision": float(round(prec, 4)),
        "f1": float(round(f1, 4))
    })

print("FOLD-BY-FOLD METRICS FOR ARCH_C_log_c500:")
for fm in fold_metrics:
    print(f"  Fold {fm['fold']}: Fraud={fm['total_fraud']}, TP={fm['tp']}, FP={fm['fp']}, FN={fm['fn']}, Recall={fm['recall']:.2%}, Precision={fm['precision']:.2%}, F1={fm['f1']:.4f}")

recs = [fm["recall"] for fm in fold_metrics]
precs = [fm["precision"] for fm in fold_metrics]
f1s = [fm["f1"] for fm in fold_metrics]
print("\nSUMMARY:")
print(f"  Recall   : Mean = {np.mean(recs):.4f}, Std = {np.std(recs):.4f}, Min = {np.min(recs):.4f}, Max = {np.max(recs):.4f}")
print(f"  Precision: Mean = {np.mean(precs):.4f}, Std = {np.std(precs):.4f}, Min = {np.min(precs):.4f}, Max = {np.max(precs):.4f}")
print(f"  F1-Score : Mean = {np.mean(f1s):.4f}, Std = {np.std(f1s):.4f}")
