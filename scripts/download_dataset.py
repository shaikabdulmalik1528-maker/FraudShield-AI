"""
FraudShield AI - Dataset Acquisition Script
Downloads the European Credit Card Fraud dataset from Kaggle via authorized kagglehub API
or guides the user on manual placement.
"""

import os
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
TARGET_FILE = RAW_DIR / "creditcard.csv"

def acquire_dataset():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    if TARGET_FILE.exists():
        size_mb = TARGET_FILE.stat().st_size / (1024 * 1024)
        print(f"[SUCCESS] Dataset already exists at: {TARGET_FILE} ({size_mb:.2f} MB)")
        return str(TARGET_FILE)

    print("[INFO] Checking automated download via kagglehub...")
    try:
        import kagglehub
        path = kagglehub.dataset_download("mlg-ulb/creditcardfraud")
        downloaded_dir = Path(path)
        csv_candidates = list(downloaded_dir.glob("*.csv"))
        
        if csv_candidates:
            src = csv_candidates[0]
            print(f"[INFO] Found downloaded file at: {src}")
            shutil.copy(src, TARGET_FILE)
            print(f"[SUCCESS] Dataset placed at: {TARGET_FILE}")
            return str(TARGET_FILE)
        else:
            print(f"[WARNING] Downloaded path {downloaded_dir} contained no CSV files.")
    except Exception as e:
        print(f"[INFO] Automated download failed or requires Kaggle login: {e}")

    print("\n" + "=" * 70)
    print("MANUAL DATASET ACQUISITION INSTRUCTIONS:")
    print("1. Visit https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud")
    print("2. Download the archive (creditcardfraud.zip) and extract 'creditcard.csv'")
    print(f"3. Place 'creditcard.csv' directly into: {RAW_DIR}")
    print("=" * 70 + "\n")
    return None

if __name__ == "__main__":
    acquire_dataset()
