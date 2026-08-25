#!/usr/bin/env python3
"""
Generate synthetic Indian‑style datasets with hidden cross‑table relationships.
Creates:
    persons.csv, calls.csv, transactions.csv, fir_text.csv, locations.csv
"""

import csv
import random
from pathlib import Path
from faker import Faker

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
OUT_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\synthetic dataset")
N_PERSONS = 500
N_CALLS   = 2000
N_TXNS    = 1500
N_FIRS    = 300
N_LOCS    = 200

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
fake = Faker("en_IN")
random.seed(42)
Faker.seed(42)

# Indian states + major cities for realistic locations
STATES = [
    ("Maharashtra", "Mumbai"), ("Delhi", "New Delhi"), ("Karnataka", "Bengaluru"),
    ("Tamil Nadu", "Chennai"), ("Uttar Pradesh", "Lucknow"), ("Gujarat", "Ahmedabad"),
    ("West Bengal", "Kolkata"), ("Rajasthan", "Jaipur"), ("Telangana", "Hyderabad"),
    ("Madhya Pradesh", "Bhopal")
]

# ----------------------------------------------------------------------
# 1️ locations.csv
# ----------------------------------------------------------------------
def gen_locations():
    rows = []
    for i in range(1, N_LOCS + 1):
        state, city = random.choice(STATES)
        rows.append({
            "location_id": i,
            "state": state,
            "city": city,
            "latitude": round(random.uniform(8.0, 37.0), 6),
            "longitude": round(random.uniform(68.0, 97.0), 6)
        })
    return rows

# ----------------------------------------------------------------------
# 2️ persons.csv  (hidden rings)
# ----------------------------------------------------------------------
def gen_persons(locations):
    rows = []
    # Create a few "criminal rings" – each ring shares a location and phone prefix
    rings = 5
    ring_members = {r: [] for r in range(rings)}

    for pid in range(1, N_PERSONS + 1):
        ring = random.randrange(rings) if random.random() < 0.3 else None
        loc = random.choice(locations)
        name = fake.name()
        phone = f"+91-{random.randint(7000000000, 9999999999)}"
        aadhar = f"{random.randint(100000000000, 999999999999)}"
        rows.append({
            "person_id": pid,
            "name": name,
            "phone": phone,
            "aadhar": aadhar,
            "address": fake.street_address(),
            "city": loc["city"],
            "state": loc["state"],
            "location_id": loc["location_id"],
            "ring_id": ring if ring is not None else ""
        })
        if ring is not None:
            ring_members[ring].append(pid)

    # Ensure each ring has at least 3 members (for hidden relationship proof)
    for ring, members in ring_members.items():
        while len(members) < 3:
            pid = len(rows) + 1
            loc = random.choice(locations)
            rows.append({
                "person_id": pid,
                "name": fake.name(),
                "phone": f"+91-{random.randint(7000000000, 9999999999)}",
                "aadhar": f"{random.randint(100000000000, 999999999999)}",
                "address": fake.street_address(),
                "city": loc["city"],
                "state": loc["state"],
                "location_id": loc["location_id"],
                "ring_id": ring
            })
            members.append(pid)

    return rows, ring_members

# ----------------------------------------------------------------------
# 3️ calls.csv  (caller/callee from persons, some intra‑ring calls)
# ----------------------------------------------------------------------
def gen_calls(persons, ring_members):
    person_ids = [p["person_id"] for p in persons]
    rows = []
    for cid in range(1, N_CALLS + 1):
        caller = random.choice(person_ids)
        callee = random.choice(person_ids)
        while callee == caller:
            callee = random.choice(person_ids)

        # boost probability of intra‑ring calls
        caller_ring = next((p["ring_id"] for p in persons if p["person_id"] == caller), None)
        callee_ring = next((p["ring_id"] for p in persons if p["person_id"] == callee), None)
        # treat empty string as no ring
        caller_ring = caller_ring if caller_ring else None
        callee_ring = callee_ring if callee_ring else None
        if caller_ring and caller_ring == callee_ring and random.random() < 0.6:
            pass  # keep as‑is
        else:
            if random.random() < 0.1 and caller_ring is not None:
                # force a cross‑ring call occasionally
                callee = random.choice(ring_members[caller_ring])

        rows.append({
            "call_id": cid,
            "caller_id": caller,
            "callee_id": callee,
            "start_time": fake.date_time_between(start_date="-30d", end_date="now").isoformat(),
            "duration_sec": random.randint(5, 3600),
            "cell_tower_id": random.randint(1000, 9999)
        })
    return rows

# ----------------------------------------------------------------------
# 4️ transactions.csv  (sender/receiver from persons, some intra‑ring)
# ----------------------------------------------------------------------
def gen_transactions(persons, ring_members):
    person_ids = [p["person_id"] for p in persons]
    rows = []
    for tid in range(1, N_TXNS + 1):
        sender = random.choice(person_ids)
        receiver = random.choice(person_ids)
        while receiver == sender:
            receiver = random.choice(person_ids)

        sender_ring = next((p["ring_id"] for p in persons if p["person_id"] == sender), None)
        receiver_ring = next((p["ring_id"] for p in persons if p["person_id"] == receiver), None)
        sender_ring = sender_ring if sender_ring else None
        receiver_ring = receiver_ring if receiver_ring else None

        if sender_ring and sender_ring == receiver_ring and random.random() < 0.5:
            pass
        else:
            if random.random() < 0.1 and sender_ring is not None:
                receiver = random.choice(ring_members[sender_ring])

        rows.append({
            "txn_id": tid,
            "sender_id": sender,
            "receiver_id": receiver,
            "amount_inr": round(random.uniform(100, 5_00_000), 2),
            "txn_time": fake.date_time_between(start_date="-60d", end_date="now").isoformat(),
            "mode": random.choice(["UPI", "NEFT", "IMPS", "CASH", "CARD"]),
            "bank_ref": fake.bban()
        })
    return rows

# ----------------------------------------------------------------------
# 5️ fir_text.csv  (free‑text FIRs referencing persons & locations)
# ----------------------------------------------------------------------
def gen_firs(persons, locations):
    rows = []
    for fid in range(1, N_FIRS + 1):
        # pick a random person as complainant, another as accused (maybe same ring)
        complainant = random.choice(persons)
        accused = random.choice(persons)
        loc = random.choice(locations)

        # embed hidden link: if both belong to same ring, mention it implicitly
        ring_note = ""
        if complainant["ring_id"] and complainant["ring_id"] == accused["ring_id"]:
            ring_note = " The accused is known to associate with the complainant's circle."

        narrative = (
            f"FIR No {fid}: On {fake.date_between(start_date='-90d', end_date='today')} "
            f"{complainant['name']} (Aadhar {complainant['aadhar']}) reported a theft at "
            f"{loc['city']}, {loc['state']}. Suspect {accused['name']} (Phone {accused['phone']}) "
            f"was seen near the scene.{ring_note}"
        )
        rows.append({
            "fir_id": fid,
            "date": fake.date_between(start_date='-90d', end_date='today').isoformat(),
            "complainant_id": complainant["person_id"],
            "accused_id": accused["person_id"],
            "location_id": loc["location_id"],
            "narrative": narrative
        })
    return rows

# ----------------------------------------------------------------------
# CSV writer
# ----------------------------------------------------------------------
def write_csv(filename, fieldnames, rows):
    path = OUT_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] {filename} -> {len(rows)} rows")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    locations = gen_locations()
    write_csv("locations.csv",
              ["location_id","state","city","latitude","longitude"], locations)

    persons, ring_members = gen_persons(locations)
    write_csv("persons.csv",
              ["person_id","name","phone","aadhar","address","city","state","location_id","ring_id"], persons)

    calls = gen_calls(persons, ring_members)
    write_csv("calls.csv",
              ["call_id","caller_id","callee_id","start_time","duration_sec","cell_tower_id"], calls)

    txns = gen_transactions(persons, ring_members)
    write_csv("transactions.csv",
              ["txn_id","sender_id","receiver_id","amount_inr","txn_time","mode","bank_ref"], txns)

    firs = gen_firs(persons, locations)
    write_csv("fir_text.csv",
              ["fir_id","date","complainant_id","accused_id","location_id","narrative"], firs)

    print("\nAll files written to:", OUT_DIR)

if __name__ == "__main__":
    main()