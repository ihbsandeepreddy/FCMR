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

Performance: Uses DuckDB self-joins for exact-match fields (O(n log n)) and an
inverted-token index for address fuzzy matching (O(n × avg_tokens)), replacing
the previous O(n²) nested Python loop that stalled on datasets above ~10K rows.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

import duckdb
import polars as pl

from fcmr_core.config import apply_duckdb_limits, settings
from fcmr_core.rules.registry import register


def _hash_aadhaar(raw: str) -> str:
    val = (raw or "").strip().replace(" ", "").replace("-", "")
    if not val or len(val) != 12:
        return ""
    salted = settings.aadhaar_hash_salt + val
    return hashlib.sha256(salted.encode()).hexdigest()


def _normalize_address(addr: str) -> str:
    return (addr or "").strip().upper()


def _address_similarity(a1: str, a2: str) -> float:
    """Token-set Jaccard similarity for addresses. Returns [0.0, 1.0]."""
    if not a1 or not a2:
        return 0.0
    t1 = set(_normalize_address(a1).split())
    t2 = set(_normalize_address(a2).split())
    if not t1 or not t2:
        return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

    def groups(self) -> dict[int, list[int]]:
        result: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            result[self.find(i)].append(i)
        return result


def _col_list(df: pl.DataFrame, col: str) -> list[str]:
    if col not in df.columns:
        return [""] * len(df)
    return df[col].cast(pl.Utf8, strict=False).fill_null("").to_list()


def _exact_pairs_duckdb(keys: list[str]) -> list[tuple[int, int]]:
    """Return (i, j) index pairs where i < j and keys[i] == keys[j] (both non-empty)."""
    if not any(keys):
        return []
    work = pl.DataFrame({"_idx": list(range(len(keys))), "_key": keys})
    with duckdb.connect() as con:
        apply_duckdb_limits(con)
        con.register("tbl", work.to_arrow())
        rows = con.execute("""
            SELECT a._idx, b._idx
            FROM tbl a
            JOIN tbl b ON a._key = b._key
            WHERE a._key IS NOT NULL AND a._key <> ''
              AND a._idx < b._idx
        """).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


def _address_candidate_pairs(addrs: list[str], min_shared: int = 3) -> list[tuple[int, int]]:
    """Find candidate address pairs via inverted-token index.

    Only pairs sharing ≥min_shared long tokens (≥4 chars) are returned.
    Very common tokens (bucket size > 500) are skipped to avoid noise.
    """
    tok_idx: dict[str, list[int]] = {}
    for i, addr in enumerate(addrs):
        normalized = (addr or "").strip().upper()
        if not normalized:
            continue
        tokens = {w for w in normalized.split() if len(w) >= 4}
        for tok in tokens:
            tok_idx.setdefault(tok, []).append(i)

    pair_counts: dict[tuple[int, int], int] = {}
    for bucket in tok_idx.values():
        if len(bucket) > 500:  # Skip very common tokens (ROAD, NAGAR, INDIA…)
            continue
        for ii in range(len(bucket)):
            for jj in range(ii + 1, len(bucket)):
                p = (min(bucket[ii], bucket[jj]), max(bucket[ii], bucket[jj]))
                pair_counts[p] = pair_counts.get(p, 0) + 1

    return [p for p, c in pair_counts.items() if c >= min_shared]


def _check_kyc_consistency(group_rows: list[dict]) -> bool:
    if not group_rows:
        return True
    pans, aadhs, voter_ids, emails, mobiles, states, pincodes = set(), set(), set(), set(), set(), set(), set()
    for row in group_rows:
        if v := (row.get("pan") or "").strip().upper():
            pans.add(v)
        if v := _hash_aadhaar(row.get("aadhaar") or ""):
            aadhs.add(v)
        if v := (row.get("voter_id") or "").strip().upper():
            voter_ids.add(v)
        if v := (row.get("email") or "").strip().lower():
            emails.add(v)
        if v := (row.get("mobile") or "").strip().replace(" ", "").replace("-", ""):
            mobiles.add(v)
        if v := (row.get("state") or "").strip().upper():
            states.add(v)
        if v := (row.get("pincode") or "").strip():
            pincodes.add(v)
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
    sorted_indices = ",".join(str(i) for i in sorted(indices))
    return hashlib.sha256(sorted_indices.encode()).hexdigest()[:16]


@register("ucid", "UCID grouping and KYC consistency check")
def rule_ucid(df: pl.DataFrame) -> pl.DataFrame:
    n = len(df)
    uf = UnionFind(n)

    # --- Exact-match fields: use DuckDB self-join (O(n log n)) ---

    pans = [v.strip().upper() for v in _col_list(df, "pan")]
    for i, j in _exact_pairs_duckdb(pans):
        uf.union(i, j)

    aadh_hashes = [_hash_aadhaar(v) for v in _col_list(df, "aadhaar")]
    for i, j in _exact_pairs_duckdb(aadh_hashes):
        uf.union(i, j)

    vids = [v.strip().upper() for v in _col_list(df, "voter_id")]
    for i, j in _exact_pairs_duckdb(vids):
        uf.union(i, j)

    names = _col_list(df, "full_name")
    dobs = _col_list(df, "dob")
    nd_keys = [
        (n.strip().upper() + "|" + d.strip()) if n.strip() and d.strip() else ""
        for n, d in zip(names, dobs)
    ]
    for i, j in _exact_pairs_duckdb(nd_keys):
        uf.union(i, j)

    accts = [v.strip() for v in _col_list(df, "bank_account")]
    for i, j in _exact_pairs_duckdb(accts):
        uf.union(i, j)

    # --- Address fuzzy: token-bucket candidates → Jaccard check ---
    addrs = _col_list(df, "address_line1")
    for i, j in _address_candidate_pairs(addrs):
        if _address_similarity(addrs[i], addrs[j]) >= 0.85:
            uf.union(i, j)

    # --- Assign UCIDs ---
    groups = uf.groups()
    ucid_map = {root: _create_stable_ucid(members) for root, members in groups.items()}
    ucids = [ucid_map[uf.find(i)] for i in range(n)]
    ucid_sizes = [len(groups[uf.find(i)]) for i in range(n)]

    # --- KYC consistency: only read the 7 KYC columns (not all columns) ---
    kyc_cols = ["pan", "aadhaar", "voter_id", "email", "mobile", "state", "pincode"]
    rows = [
        {col: (df[col][i] if col in df.columns else None) for col in kyc_cols}
        for i in range(n)
    ]

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
            descs.append(
                f"UCID {ucids[i]} has conflicting KYC data (PAN, Aadhaar, Voter ID, email, mobile, state, or pincode)"
            )

    return df.with_columns([
        pl.Series("ucid", ucids, dtype=pl.Utf8),
        pl.Series("ucid_size", ucid_sizes, dtype=pl.Int32),
        pl.Series("_exc_ucid_status", statuses, dtype=pl.Utf8),
        pl.Series("_exc_ucid_code", codes, dtype=pl.Utf8),
        pl.Series("_exc_ucid_desc", descs, dtype=pl.Utf8),
    ])
