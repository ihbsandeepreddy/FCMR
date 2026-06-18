"""UCID (Unique Customer Identifier) creation via union-find grouping.

Groups rows based on matching:
  1. PAN (exact)
  2. Aadhaar hash (salted)
  3. Voter ID (exact)
  4. Name+DOB (normalised exact)
  5. Bank Account (exact)
  6. Address (fuzzy token-set similarity ≥0.85)

Emits a stable UCID per connected component and flags KYC inconsistencies
within the same UCID (conflicting PAN, Aadhaar, Voter ID, email, mobile, etc).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

import polars as pl

from fcmr_core.config import settings
from fcmr_core.rules.registry import register


def _hash_aadhaar(raw: str) -> str:
    """One-way hash of Aadhaar for dedup."""
    val = (raw or "").strip().replace(" ", "").replace("-", "")
    if not val or len(val) != 12:
        return ""
    salted = settings.aadhaar_hash_salt + val
    return hashlib.sha256(salted.encode()).hexdigest()


def _normalize_address(addr: str) -> str:
    """Normalize address for fuzzy comparison."""
    return (addr or "").strip().upper()


def _address_similarity(a1: str, a2: str) -> float:
    """Token-set Jaccard similarity for addresses. Returns [0.0, 1.0]."""
    if not a1 or not a2:
        return 0.0
    # Split into tokens, normalize
    t1 = set(_normalize_address(a1).split())
    t2 = set(_normalize_address(a2).split())
    if not t1 or not t2:
        return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0


class UnionFind:
    """Union-find (disjoint-set) data structure for grouping."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        # Union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

    def groups(self) -> dict[int, list[int]]:
        """Return {root: [members]}."""
        result: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            result[self.find(i)].append(i)
        return result


def _should_connect(row1: dict, row2: dict, idx1: int, idx2: int) -> bool:
    """Check if two rows should be connected in the UCID group."""
    # Exact PAN match
    pan1 = (row1.get("pan") or "").strip().upper()
    pan2 = (row2.get("pan") or "").strip().upper()
    if pan1 and pan1 == pan2:
        return True

    # Aadhaar hash match
    aadh1 = _hash_aadhaar(row1.get("aadhaar") or "")
    aadh2 = _hash_aadhaar(row2.get("aadhaar") or "")
    if aadh1 and aadh1 == aadh2:
        return True

    # Voter ID match
    vid1 = (row1.get("voter_id") or "").strip().upper()
    vid2 = (row2.get("voter_id") or "").strip().upper()
    if vid1 and vid1 == vid2:
        return True

    # Name+DOB match
    name1 = (row1.get("full_name") or "").strip().upper()
    dob1 = (row1.get("dob") or "").strip()
    name2 = (row2.get("full_name") or "").strip().upper()
    dob2 = (row2.get("dob") or "").strip()
    if name1 and dob1 and name1 == name2 and dob1 == dob2:
        return True

    # Bank account match
    acct1 = (row1.get("bank_account") or "").strip()
    acct2 = (row2.get("bank_account") or "").strip()
    if acct1 and acct1 == acct2:
        return True

    # Address fuzzy match (token-set Jaccard >= 0.85)
    addr1 = row1.get("address_line1") or ""
    addr2 = row2.get("address_line1") or ""
    if _address_similarity(addr1, addr2) >= 0.85:
        return True

    return False


def _check_kyc_consistency(group_rows: list[dict]) -> bool:
    """Check if all rows in a UCID group have consistent KYC data."""
    if not group_rows:
        return True

    # Collect unique values per KYC field
    pans = set()
    aadhs = set()
    voter_ids = set()
    emails = set()
    mobiles = set()
    states = set()
    pincodes = set()

    for row in group_rows:
        pan = (row.get("pan") or "").strip().upper()
        if pan:
            pans.add(pan)

        aadh = _hash_aadhaar(row.get("aadhaar") or "")
        if aadh:
            aadhs.add(aadh)

        vid = (row.get("voter_id") or "").strip().upper()
        if vid:
            voter_ids.add(vid)

        email = (row.get("email") or "").strip().lower()
        if email:
            emails.add(email)

        mobile = (row.get("mobile") or "").strip().replace(" ", "").replace("-", "")
        if mobile:
            mobiles.add(mobile)

        state = (row.get("state") or "").strip().upper()
        if state:
            states.add(state)

        pincode = (row.get("pincode") or "").strip()
        if pincode:
            pincodes.add(pincode)

    # Check for conflicts: more than one value for a field means inconsistency
    return (
        len(pans) <= 1
        and len(aadhs) <= 1
        and len(voter_ids) <= 1
        and len(emails) <= 1
        and len(mobiles) <= 1
        and len(states) <= 1
        and len(pincodes) <= 1
    )


def _create_stable_ucid(indices: list[int]) -> str:
    """Create a stable UCID hash from sorted indices."""
    sorted_indices = ",".join(str(i) for i in sorted(indices))
    return hashlib.sha256(sorted_indices.encode()).hexdigest()[:16]


@register("ucid", "UCID grouping and KYC consistency check")
def rule_ucid(df: pl.DataFrame) -> pl.DataFrame:
    """Create UCIDs via union-find and flag KYC inconsistencies."""
    n = len(df)
    uf = UnionFind(n)

    # Convert to list of dicts for easier access
    rows = [
        {col: val for col, val in zip(df.columns, row)} for row in zip(*[df[col].to_list() for col in df.columns])
    ]

    # Connect rows based on matching criteria
    for i in range(n):
        for j in range(i + 1, n):
            if _should_connect(rows[i], rows[j], i, j):
                uf.union(i, j)

    # Assign UCIDs to each group
    groups = uf.groups()
    ucid_map = {root: _create_stable_ucid(members) for root, members in groups.items()}

    ucids = [ucid_map[uf.find(i)] for i in range(n)]
    ucid_sizes = [len(groups[uf.find(i)]) for i in range(n)]

    # Check KYC consistency per group
    statuses, codes, descs = [], [], []
    for i in range(n):
        root = uf.find(i)
        group_indices = groups[root]
        group_rows = [rows[idx] for idx in group_indices]

        if _check_kyc_consistency(group_rows):
            statuses.append("OK")
            codes.append("")
            descs.append("")
        else:
            statuses.append("WARN")
            codes.append("UCID_KYC_INCONSISTENT")
            descs.append(f"UCID {ucids[i]} has conflicting KYC data (PAN, Aadhaar, Voter ID, email, mobile, state, or pincode)")

    # Annotate with UCID, size, and consistency
    result = df.with_columns([
        pl.Series("ucid", ucids, dtype=pl.Utf8),
        pl.Series("ucid_size", ucid_sizes, dtype=pl.Int32),
        pl.Series("_exc_ucid_status", statuses, dtype=pl.Utf8),
        pl.Series("_exc_ucid_code", codes, dtype=pl.Utf8),
        pl.Series("_exc_ucid_desc", descs, dtype=pl.Utf8),
    ])

    return result
