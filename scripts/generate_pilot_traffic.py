"""
FraudShield 3.0 Reproducible Synthetic Pilot Traffic Generator.
Generates >= 2,000 realistic, fully labeled synthetic transactions across 7 operational scenarios:
1. Legitimate Payments (80% / 2,000 transactions across 500 distinct cardholders)
2. Velocity Attacks (Targeted cardholder subjected to burst frequency > 10 txs / 2 mins)
3. Impossible Travel (Physical POS swipe transactions separated by > 800 km/h)
4. Duplicate Replay Attacks (Identical transaction IDs submitted within 31-day window)
5. Multi-Currency Operations (JPY, EUR, GBP, CAD, AUD, INR with realistic FX)
6. High-Value Extreme Anomalies (Whale amounts $3,500 - $18,000)
7. Degraded Store / Failsafe Invocations (Threshold boundary testing)

Guarantees:
- 100% mathematically valid Luhn Mod-10 PANs across Visa, Mastercard, and Amex.
- Realistic cardholder pool (500 cards for legitimate commerce to prevent artificial velocity saturation).
- Complete UTC ISO-8601 timestamps.
- Explicit ground-truth labels for precision/recall/F1/FPR/FNR evaluation.
"""

import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_synthetic_transactions.json"

# Deterministic Seed
RANDOM_SEED = 2026
random.seed(RANDOM_SEED)


def generate_luhn_pan(prefix: str = "453200", length: int = 16) -> str:
    """Generates a mathematically valid Luhn Mod-10 Primary Account Number."""
    digits = [int(c) for c in prefix]
    while len(digits) < length - 1:
        digits.append(random.randint(0, 9))

    rev = digits[::-1]
    checksum = 0
    for idx, d in enumerate(rev):
        if idx % 2 == 0:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d

    check_digit = (10 - (checksum % 10)) % 10
    digits.append(check_digit)
    return "".join(str(d) for d in digits)


# Generate pools of verified Luhn card PANs
VISA_POOL = [generate_luhn_pan("453200", 16) for _ in range(300)]
MC_POOL = [generate_luhn_pan("542500", 16) for _ in range(150)]
AMEX_POOL = [generate_luhn_pan("378200", 15) for _ in range(50)]
LEGIT_CARD_POOL = VISA_POOL + MC_POOL + AMEX_POOL

# Dedicated test cards for specific attack scenarios
ATTACK_CARD_VELOCITY = generate_luhn_pan("455673", 16)
ATTACK_CARD_TRAVEL = generate_luhn_pan("510510", 16)
ATTACK_CARD_ANOMALY = generate_luhn_pan("491699", 16)

MERCHANTS = [
    {"id": "merch_grocery_01", "mcc": "5411", "name": "Supermarket Prime", "risk": "low"},
    {"id": "merch_dining_02", "mcc": "5812", "name": "City Bistro", "risk": "low"},
    {"id": "merch_gas_03", "mcc": "5541", "name": "Highway Fuel Station", "risk": "low"},
    {"id": "merch_apparel_04", "mcc": "5651", "name": "Urban Outfitters", "risk": "medium"},
    {"id": "merch_electronics_05", "mcc": "5732", "name": "Apex Electronics", "risk": "medium"},
    {"id": "merch_travel_06", "mcc": "4722", "name": "Global Air Tours", "risk": "medium"},
    {"id": "merch_digital_07", "mcc": "5815", "name": "Digital Downloads Hub", "risk": "medium"},
    {"id": "merch_crypto_08", "mcc": "6051", "name": "Crypto Exchange Direct", "risk": "high"},
    {"id": "merch_gambling_09", "mcc": "7995", "name": "Royal Casino Online", "risk": "high"},
    {"id": "merch_wire_10", "mcc": "4829", "name": "Wire Remit Fast", "risk": "high"},
]

CITIES = [
    {"city": "New York", "lat": 40.7128, "lon": -74.0060},
    {"city": "London", "lat": 51.5074, "lon": -0.1278},
    {"city": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    {"city": "San Francisco", "lat": 37.7749, "lon": -122.4194},
    {"city": "Paris", "lat": 48.8566, "lon": 2.3522},
    {"city": "Sydney", "lat": -33.8688, "lon": 151.2093},
    {"city": "Chicago", "lat": 41.8781, "lon": -87.6298},
]


def generate_synthetic_dataset() -> List[Dict[str, Any]]:
    dataset = []
    base_time = datetime(2026, 11, 15, 0, 0, 0, tzinfo=timezone.utc)
    current_time = base_time

    # --------------------------------------------------------------------------
    # Scenario 1: Legitimate Payments (2,000 transactions across 500 cards)
    # --------------------------------------------------------------------------
    print("[1/7] Generating Scenario 1: 2,000 Legitimate Payments across 500 cardholders...")
    for i in range(2000):
        # Spaced out by 2-5 minutes across 500 cards so hourly velocity per card is 1-2 txs
        current_time += timedelta(seconds=random.randint(45, 180))
        pan = LEGIT_CARD_POOL[i % len(LEGIT_CARD_POOL)]
        merch = random.choice(MERCHANTS[:7])  # low/medium risk merchants
        city = random.choice(CITIES)
        amount = round(random.uniform(5.50, 180.00), 2)

        tx = {
            "transaction_id": f"tx_legit_{i:04d}",
            "timestamp": current_time.isoformat(),
            "amount": amount,
            "currency": "USD",
            "card_number": pan,
            "merchant_id": merch["id"],
            "mcc": merch["mcc"],
            "channel": random.choice(["ECOMMERCE", "POS", "MOBILE"]),
            "terminal_id": f"term_{random.randint(100, 999)}",
            "latitude": city["lat"] + random.uniform(-0.05, 0.05),
            "longitude": city["lon"] + random.uniform(-0.05, 0.05),
            "card_present": True if random.random() > 0.4 else False,
            "cvv_provided": True,
            "ground_truth": {
                "is_fraud": False,
                "scenario": "LEGITIMATE_PAYMENT",
                "expected_action": "APPROVE"
            }
        }
        dataset.append(tx)

    # --------------------------------------------------------------------------
    # Scenario 2: Velocity Attacks (CNP burst frequency) - 100 transactions
    # --------------------------------------------------------------------------
    print("[2/7] Generating Scenario 2: 100 Velocity Attack Transactions on targeted cards...")
    burst_time = current_time + timedelta(hours=1)

    for burst_batch in range(10):
        burst_card = generate_luhn_pan("455673", 16)
        burst_time += timedelta(minutes=30)
        for b_idx in range(10):
            burst_time += timedelta(seconds=random.randint(2, 6))
            is_fraud = (b_idx >= 2)  # After 2 transactions within 10 seconds, velocity is fraudulent
            tx = {
                "transaction_id": f"tx_velo_{burst_batch}_{b_idx}",
                "timestamp": burst_time.isoformat(),
                "amount": round(random.uniform(150.00, 650.00), 2),
                "currency": "USD",
                "card_number": burst_card,
                "merchant_id": "merch_electronics_05",
                "mcc": "5732",
                "channel": "ECOMMERCE",
                "card_present": False,
                "cvv_provided": True,
                "ground_truth": {
                    "is_fraud": is_fraud,
                    "scenario": "VELOCITY_ATTACK",
                    "expected_action": "DECLINE" if b_idx >= 4 else "STEP_UP_2FA"
                }
            }
            dataset.append(tx)

    # --------------------------------------------------------------------------
    # Scenario 3: Impossible Travel Attacks (POS Swipe) - 50 transactions
    # --------------------------------------------------------------------------
    print("[3/7] Generating Scenario 3: 50 Impossible Travel Transactions...")
    geo_time = burst_time + timedelta(hours=2)

    for g_idx in range(25):
        geo_time += timedelta(hours=1)
        geo_card = generate_luhn_pan("510510", 16)

        # Legitimate initial physical swipe in New York
        tx1 = {
            "transaction_id": f"tx_geo_anchor_{g_idx}",
            "timestamp": geo_time.isoformat(),
            "amount": round(random.uniform(20.0, 75.0), 2),
            "currency": "USD",
            "card_number": geo_card,
            "merchant_id": "merch_dining_02",
            "mcc": "5812",
            "channel": "POS",
            "terminal_id": "term_ny_01",
            "latitude": 40.7128,
            "longitude": -74.0060,  # NYC
            "card_present": True,
            "ground_truth": {
                "is_fraud": False,
                "scenario": "GEO_ANCHOR",
                "expected_action": "APPROVE"
            }
        }
        dataset.append(tx1)

        # Impossible swipe 15 minutes later in London (5,570 km away => ~22,000 km/h)
        geo_time += timedelta(minutes=15)
        tx2 = {
            "transaction_id": f"tx_geo_impossible_{g_idx}",
            "timestamp": geo_time.isoformat(),
            "amount": round(random.uniform(250.0, 950.0), 2),
            "currency": "USD",
            "card_number": geo_card,
            "merchant_id": "merch_apparel_04",
            "mcc": "5651",
            "channel": "POS",
            "terminal_id": "term_lon_02",
            "latitude": 51.5074,
            "longitude": -0.1278,  # London
            "card_present": True,
            "ground_truth": {
                "is_fraud": True,
                "scenario": "IMPOSSIBLE_TRAVEL",
                "expected_action": "IMMEDIATE_BLOCK"
            }
        }
        dataset.append(tx2)

    # --------------------------------------------------------------------------
    # Scenario 4: Duplicate Replay Attacks - 50 transactions
    # --------------------------------------------------------------------------
    print("[4/7] Generating Scenario 4: 50 Duplicate Replay Transactions...")
    dup_time = geo_time + timedelta(hours=2)
    for d_idx in range(25):
        dup_time += timedelta(minutes=10)
        orig_id = f"tx_dup_orig_{d_idx}"
        dup_card = generate_luhn_pan("401288", 16)
        tx_orig = {
            "transaction_id": orig_id,
            "timestamp": dup_time.isoformat(),
            "amount": round(random.uniform(45.0, 180.0), 2),
            "currency": "USD",
            "card_number": dup_card,
            "merchant_id": "merch_grocery_01",
            "mcc": "5411",
            "channel": "ECOMMERCE",
            "ground_truth": {
                "is_fraud": False,
                "scenario": "ORIGINAL_FOR_REPLAY",
                "expected_action": "APPROVE"
            }
        }
        dataset.append(tx_orig)

        # Exact replayed duplicate transaction
        dup_time += timedelta(seconds=random.randint(5, 30))
        tx_replay = dict(tx_orig)
        tx_replay["timestamp"] = dup_time.isoformat()
        tx_replay["ground_truth"] = {
            "is_fraud": True,
            "scenario": "DUPLICATE_REPLAY",
            "expected_action": "IMMEDIATE_BLOCK"
        }
        dataset.append(tx_replay)

    # --------------------------------------------------------------------------
    # Scenario 5: Multi-Currency Global Payments - 150 transactions
    # --------------------------------------------------------------------------
    print("[5/7] Generating Scenario 5: 150 Multi-Currency Operations...")
    currencies = [
        ("EUR", 15.0, 250.0, False),
        ("GBP", 10.0, 200.0, False),
        ("JPY", 2000.0, 35000.0, False),
        ("CAD", 25.0, 300.0, False),
        ("AUD", 30.0, 350.0, False),
        ("INR", 1000.0, 15000.0, False),
        ("EUR", 8000.0, 20000.0, True),  # Fraudulent extreme multi-currency
        ("GBP", 6000.0, 15000.0, True),  # Fraudulent extreme multi-currency
    ]

    curr_time = dup_time + timedelta(hours=3)
    for c_idx in range(150):
        curr_time += timedelta(minutes=2)
        curr, min_amt, max_amt, is_fraud = random.choice(currencies)
        amt = round(random.uniform(min_amt, max_amt), 2)
        pan = generate_luhn_pan("491699", 16)
        merch = random.choice(MERCHANTS)

        tx = {
            "transaction_id": f"tx_fx_{c_idx}",
            "timestamp": curr_time.isoformat(),
            "amount": amt,
            "currency": curr,
            "card_number": pan,
            "merchant_id": merch["id"],
            "mcc": merch["mcc"],
            "channel": "ECOMMERCE",
            "ground_truth": {
                "is_fraud": is_fraud,
                "scenario": "MULTI_CURRENCY",
                "expected_action": "DECLINE" if is_fraud else "APPROVE"
            }
        }
        dataset.append(tx)

    # --------------------------------------------------------------------------
    # Scenario 6: High-Value Extreme Anomalies - 100 transactions
    # --------------------------------------------------------------------------
    print("[6/7] Generating Scenario 6: 100 Extreme Anomaly Transactions...")
    anom_time = curr_time + timedelta(hours=2)
    for a_idx in range(100):
        anom_time += timedelta(minutes=5)
        is_fraud = (a_idx < 60)
        pan = generate_luhn_pan("520082", 16)
        merch = random.choice(MERCHANTS[7:]) if is_fraud else random.choice(MERCHANTS[4:6])

        amount = round(random.uniform(4500.0, 15000.0) if is_fraud else random.uniform(1200.0, 2400.0), 2)
        tx = {
            "transaction_id": f"tx_anom_{a_idx}",
            "timestamp": anom_time.isoformat(),
            "amount": amount,
            "currency": "USD",
            "card_number": pan,
            "merchant_id": merch["id"],
            "mcc": merch["mcc"],
            "channel": "ECOMMERCE",
            "card_present": False,
            "cvv_provided": False if is_fraud else True,
            "ground_truth": {
                "is_fraud": is_fraud,
                "scenario": "HIGH_VALUE_ANOMALY",
                "expected_action": "DECLINE" if is_fraud else "MANUAL_REVIEW"
            }
        }
        dataset.append(tx)

    # --------------------------------------------------------------------------
    # Scenario 7: Degraded Store / Failsafe Invocations - 50 transactions
    # --------------------------------------------------------------------------
    print("[7/7] Generating Scenario 7: 50 Degraded Failsafe Test Transactions...")
    deg_time = anom_time + timedelta(hours=1)
    for d_idx in range(50):
        deg_time += timedelta(minutes=2)
        amounts = [80.0, 180.0, 520.0, 1200.0, 3500.0]
        amt = amounts[d_idx % len(amounts)]
        is_fraud = amt >= 3500.0
        pan = generate_luhn_pan("453200", 16)

        tx = {
            "transaction_id": f"tx_deg_{d_idx}",
            "timestamp": deg_time.isoformat(),
            "amount": amt,
            "currency": "USD",
            "card_number": pan,
            "merchant_id": "merch_grocery_01",
            "mcc": "5411",
            "channel": "ECOMMERCE",
            "ground_truth": {
                "is_fraud": is_fraud,
                "scenario": "DEGRADED_STORE_FAILSAFE",
                "expected_action": "MANUAL_REVIEW" if amt >= 3500.0 else ("STEP_UP_2FA" if amt >= 520.0 else "APPROVE")
            }
        }
        dataset.append(tx)

    total_count = len(dataset)
    fraud_count = sum(1 for t in dataset if t["ground_truth"]["is_fraud"])
    legit_count = total_count - fraud_count

    print(f"\nSynthetic Dataset Summary:")
    print(f"  Total Transactions: {total_count}")
    print(f"  Legitimate:         {legit_count} ({legit_count / total_count * 100:.1f}%)")
    print(f"  Fraud / Adversarial:{fraud_count} ({fraud_count / total_count * 100:.1f}%)")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"[SUCCESS] Synthetic pilot dataset written to: {OUTPUT_FILE}")
    return dataset


if __name__ == "__main__":
    generate_synthetic_dataset()
