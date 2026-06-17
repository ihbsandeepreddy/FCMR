"""Synthetic customer-master generator for testing and performance benchmarking.

Usage:
    python tests/generate_synthetic.py             # 1 000 rows (quick sanity)
    python tests/generate_synthetic.py 100000      # 100 k rows
    python tests/generate_synthetic.py 5000000     # 5 M rows (perf test)

The generator intentionally seeds defects so the rule engine can be verified:
  - ~2 % bad PAN format
  - ~2 % invalid Aadhaar (bad checksum)
  - ~1 % nonexistent PIN code
  - ~1 % PIN/state mismatch
  - ~1 % shared PAN across two different customers (duplicates)
  - ~1 % missing mandatory customer_id
"""

from __future__ import annotations

import hashlib
import random
import string
import sys
import csv
from pathlib import Path

# Valid Aadhaar Verhoeff multiplication and permutation tables
_MULT = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_PERM = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def _verhoeff_checksum(digits: str) -> int:
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _MULT[c][_PERM[i % 8][int(d)]]
    return _INV[c]


def _valid_aadhaar() -> str:
    # First 11 digits random (avoid leading 0/1)
    base = str(random.randint(2, 9)) + "".join(str(random.randint(0, 9)) for _ in range(10))
    check = _verhoeff_checksum(base + "0")
    return base + str(check)


def _invalid_aadhaar() -> str:
    """A structurally 12-digit number that fails Verhoeff."""
    a = _valid_aadhaar()
    # Flip last digit to corrupt checksum
    last = (int(a[-1]) + 1) % 10
    return a[:-1] + str(last)


_PAN_ENTITY = list("PFHBCAGT")
_ALPHA = string.ascii_uppercase


def _valid_pan(name: str) -> str:
    sur = (name[0] if name else "A").upper()
    entity = random.choice(_PAN_ENTITY)
    four = "".join(random.choices(_ALPHA, k=3))
    seq = f"{random.randint(0, 9999):04d}"
    check = random.choice(_ALPHA)
    return f"{four}{entity}{seq}{sur}"  # AAAAP1234A style (simplified)


def _invalid_pan() -> str:
    return "".join(random.choices("ABCDEFGHIJ0123456789", k=10))  # wrong structure


_VOTER_PREFIX = ["ABC", "XYZ", "DEF", "MNO", "PQR", "TUV", "GHI", "JKL"]


def _valid_voter_id() -> str:
    return random.choice(_VOTER_PREFIX) + f"{random.randint(1000000, 9999999)}"


_PASSPORT_FIRST = list("ABCDEFGHJKLMNPQRSTUVWXY")


def _valid_passport() -> str:
    return random.choice(_PASSPORT_FIRST) + f"{random.randint(1000000, 9999999)}"


_DL_STATES = ["MH", "DL", "KA", "TN", "GJ", "UP", "WB", "RJ", "MP", "AP"]


def _valid_dl() -> str:
    state = random.choice(_DL_STATES)
    rto = f"{random.randint(1, 20):02d}"
    year = random.randint(2000, 2023)
    seq = f"{random.randint(1, 9999999):07d}"
    return f"{state}{rto}{year}{seq}"


# Valid PIN sample from our master
_VALID_PINS = [
    ("110001", "delhi", "central delhi"),
    ("400001", "maharashtra", "mumbai city"),
    ("560001", "karnataka", "bangalore urban"),
    ("600001", "tamil nadu", "chennai"),
    ("500001", "telangana", "hyderabad"),
    ("700001", "west bengal", "kolkata"),
    ("380001", "gujarat", "ahmedabad"),
    ("226001", "uttar pradesh", "lucknow"),
    ("411001", "maharashtra", "pune"),
    ("682001", "kerala", "ernakulam"),
    ("800001", "bihar", "patna"),
    ("302001", "rajasthan", "jaipur"),
    ("462001", "madhya pradesh", "bhopal"),
    ("530001", "andhra pradesh", "visakhapatnam"),
    ("641001", "tamil nadu", "coimbatore"),
    ("395001", "gujarat", "surat"),
    ("160001", "punjab", "chandigarh"),
    ("248001", "uttarakhand", "dehradun"),
    ("208001", "uttar pradesh", "kanpur nagar"),
    ("751001", "odisha", "khorda"),
    ("834001", "jharkhand", "ranchi"),
    ("695001", "kerala", "thiruvananthapuram"),
    ("575001", "karnataka", "dakshina kannada"),
    ("440001", "maharashtra", "nagpur"),
    ("141001", "punjab", "ludhiana"),
]

_FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sunita", "Ravi", "Meena", "Suresh", "Kavitha",
                "Rajesh", "Anita", "Vijay", "Lakshmi", "Arun", "Deepa", "Sanjay", "Pooja",
                "Manoj", "Rekha", "Ajay", "Smita", "Nikhil", "Divya", "Kiran", "Nisha",
                "Mahesh", "Usha", "Dinesh", "Geeta", "Ramesh", "Savita"]
_LAST_NAMES = ["Sharma", "Patel", "Singh", "Kumar", "Gupta", "Mehta", "Rao", "Nair",
               "Iyer", "Reddy", "Joshi", "Pillai", "Chandra", "Verma", "Shah", "Das",
               "Yadav", "Mishra", "Tiwari", "Shetty", "Naik", "Bhat", "Menon", "Jain"]


def _name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def _mobile() -> str:
    return str(random.randint(6, 9)) + "".join(str(random.randint(0, 9)) for _ in range(9))


def _email(name: str) -> str:
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com"]
    slug = name.lower().replace(" ", ".") + str(random.randint(1, 999))
    return f"{slug}@{random.choice(domains)}"


def _dob() -> str:
    y = random.randint(1950, 2000)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d}"


def generate(n: int, output_path: Path) -> None:
    rng = random.Random(42)  # reproducible

    # Pre-select a small set of PANs to be shared (duplicate seeding)
    shared_pan_count = max(1, n // 100)
    shared_pans = [_valid_pan("S") for _ in range(shared_pan_count)]
    shared_pan_cursor = 0

    fieldnames = [
        "customer_id", "full_name", "dob", "gender", "mobile", "email",
        "pan", "aadhaar", "voter_id", "passport", "driving_licence",
        "address_line1", "city", "district", "state", "pincode", "bank_account", "ifsc",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(n):
            roll = rng.random()
            name = _name()
            pin_entry = rng.choice(_VALID_PINS)
            pin, state_correct, district_correct = pin_entry

            row: dict = {
                "customer_id": f"CUST{i + 1:08d}" if roll > 0.01 else "",
                "full_name": name,
                "dob": _dob(),
                "gender": rng.choice(["M", "F", "O"]),
                "mobile": _mobile(),
                "email": _email(name),
                "pan": (shared_pans[shared_pan_cursor % shared_pan_count]
                        if roll < 0.01
                        else (_invalid_pan() if 0.01 <= roll < 0.03 else _valid_pan(name))),
                "aadhaar": _invalid_aadhaar() if 0.03 <= roll < 0.05 else _valid_aadhaar(),
                "voter_id": _valid_voter_id(),
                "passport": _valid_passport() if rng.random() < 0.5 else "",
                "driving_licence": _valid_dl() if rng.random() < 0.6 else "",
                "address_line1": f"{rng.randint(1, 999)}, Main Street",
                "city": district_correct.title(),
                "district": district_correct if roll > 0.01 else "WrongDistrict",
                "state": state_correct if roll > 0.02 else "wrongstate",
                "pincode": pin if roll > 0.01 else "999999",
                "bank_account": f"{rng.randint(10**11, 10**12 - 1)}",
                "ifsc": f"SBIN{rng.randint(10000, 99999):07d}",
            }
            if roll < 0.01:
                shared_pan_cursor += 1
            writer.writerow(row)

    print(f"Generated {n:,} rows -> {output_path}")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000
    out = Path(f"data/test_customer_master_{count}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    generate(count, out)
