"""
FraudShield AI - Database Seeding Script.
Initializes database schema, creates the default administrator account,
and seeds initial transactions sampled from the authentic Kaggle dataset.
"""

import sys
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session

# Setup python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from backend.app.database import init_db, SessionLocal
from backend.app.models.user import User
from backend.app.models.transaction import Transaction
from backend.app.utils.security import get_password_hash
from backend.app.schemas.transaction import TransactionInput
from backend.app.services.transaction_service import process_and_record_transaction
from backend.app.services.fraud_engine import fraud_engine
from backend.app.utils.logger import logger

def seed_database(num_samples: int = 50):
    logger.info("Initializing schema...")
    init_db()
    db: Session = SessionLocal()

    try:
        # 1. Seed Default Administrator
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            logger.info("Creating default administrator account ('admin' / 'AdminPass123!')...")
            admin_user = User(
                username="admin",
                email="admin@fraudshield.ai",
                hashed_password=get_password_hash("AdminPass123!"),
                full_name="Chief Risk Officer",
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            logger.info("[SUCCESS] Administrator account created.")
        else:
            logger.info("Administrator account already exists.")

        # 2. Check existing transaction count
        existing_txns = db.query(Transaction).count()
        if existing_txns >= 20:
            logger.info(f"Database already contains {existing_txns} transactions. Skipping seeding.")
            return

        # 3. Load sample from raw dataset
        data_path = BASE_DIR / "data" / "raw" / "creditcard.csv"
        if not data_path.exists():
            logger.warning(f"Raw dataset not found at {data_path}. Skipping sample transaction seed.")
            return

        logger.info(f"Loading {num_samples} transactions from {data_path} to seed demonstration activity...")
        df = pd.read_csv(data_path)
        
        # Take a balanced sample: 15 fraud transactions + 35 legitimate transactions
        df_fraud = df[df["Class"] == 1].sample(n=min(15, (df["Class"] == 1).sum()), random_state=42)
        df_legit = df[df["Class"] == 0].sample(n=min(35, (df["Class"] == 0).sum()), random_state=42)
        sample_df = pd.concat([df_fraud, df_legit]).sample(frac=1.0, random_state=42) # shuffle

        # Load engine artifacts
        fraud_engine.load_artifacts()

        seeded_count = 0
        for _, row in sample_df.iterrows():
            row_dict = row.to_dict()
            row_dict.pop("Class", None)
            
            txn_in = TransactionInput(**row_dict)
            process_and_record_transaction(db, txn_in, client_ip="127.0.0.1")
            seeded_count += 1

        logger.info(f"[SUCCESS] Seeded {seeded_count} transactions and generated corresponding alerts.")

    except Exception as e:
        logger.error(f"Seeding failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
