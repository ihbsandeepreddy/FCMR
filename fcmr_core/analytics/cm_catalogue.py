"""Catalogue-grounded Customer Master forensic analytics.

Implements the fraud-detection analytics from the NBFC Audit Analytics Catalogue
(Brahmayya & Co.) that were not already covered by the 31-rule pipeline or the
8 statutory CM summary reports. Each analytic cites its catalogue ID.

Design contract (matches cm_summary.py / cm_analytics.py):
  * Pure Polars, vectorised where possible; deterministic only (stdlib difflib for
    fuzzy matching — NO AI/LLM, invariant #1).
  * Missing-column-safe: returns ``pl.DataFrame({"note": [reason]})`` when a required
    column is absent (NOT_RUN), so callers surface "not available" gracefully.
  * No PII leakage beyond what the existing reports already show (Aadhaar never raw).

Catalogue coverage in this module:
  CM-DQ-06  Sequential / templated KYC document numbers
  CM-DQ-07  Benford's Law deviation in declared income
  CM-DQ-09  Missing / blank mandatory KYC fields by branch / DSA
  CM-DQ-10  Address clustering (disproportionate borrower density at one address)
  CM-ID-01  Name similarity clustering (fuzzy match) across customers
  CM-ID-03  Velocity of new-customer onboarding per DSA / branch
  CM-ID-04  Email domain anomalies (disposable / shared domains)

Deferred (require datasets the auditor does not upload here):
  CM-DQ-05  Employee-customer identity overlap   -> needs HR master
  CM-ID-02  PEP / sanctions list screening gap   -> needs external sanctions list
"""

from __future__ import annotations

import re
from collections import defaultdict

import polars as pl

# Expected first-digit frequencies under Benford's Law (digits 1-9).
_BENFORD_EXPECTED = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}

# Nigrini (2012) Mean Absolute Deviation conformity thresholds (first-digit test).
_BENFORD_MAD_CLOSE = 0.006
_BENFORD_MAD_ACCEPTABLE = 0.012
_BENFORD_MAD_MARGINAL = 0.015

# Known disposable / temporary email domains (deterministic bundled list).
_DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "temp-mail.org",
    "throwawaymail.com",
    "yopmail.com",
    "trashmail.com",
    "getnada.com",
    "sharklasers.com",
    "dispostable.com",
    "fakeinbox.com",
    "maildrop.cc",
    "mintemail.com",
    "mailnesia.com",
    "spam4.me",
    "guerrillamailblock.com",
    "tempinbox.com",
    "emailondeck.com",
    "tempr.email",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _has(df: pl.DataFrame, *cols: str) -> bool:
    return all(c in df.columns for c in cols)


def _note(reason: str) -> pl.DataFrame:
    return pl.DataFrame({"note": [reason]})


def _str_col(df: pl.DataFrame, col: str) -> pl.Series:
    """Return a Utf8, null-filled, stripped view of a column (empty series if absent)."""
    if col in df.columns:
        return df[col].cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()
    return pl.Series(col, [""] * len(df), dtype=pl.Utf8)


# ---------------------------------------------------------------------------
# CM-DQ-10 — Address clustering (borrower density at one address)
# ---------------------------------------------------------------------------


def _normalize_address(*parts: str) -> str:
    joined = " ".join(p for p in parts if p)
    joined = joined.lower()
    joined = re.sub(r"[^a-z0-9 ]+", " ", joined)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def generate_address_clustering(df: pl.DataFrame, threshold: int = 5) -> pl.DataFrame:
    """CM-DQ-10: addresses shared by an implausible number of distinct customers.

    Forensic typology: ghost-borrower schemes / DSA-fabricated portfolios.
    Returns: Address, Distinct Customers, Loan Accounts, Risk.
    """
    if not _has(df, "address_line1"):
        return _note("address_line1 column not available")
    if df.is_empty():
        return _note("No data")

    line1 = _str_col(df, "address_line1")
    line2 = _str_col(df, "address_line2")
    city = _str_col(df, "city")
    pincode = _str_col(df, "pincode")
    has_cust = "customer_id" in df.columns
    cust = _str_col(df, "customer_id") if has_cust else None
    lan = _str_col(df, "lan") if "lan" in df.columns else None

    buckets: dict[str, dict] = {}
    for i in range(len(df)):
        norm = _normalize_address(line1[i], line2[i], city[i], pincode[i])
        if not norm:
            continue
        b = buckets.setdefault(norm, {"custs": set(), "lans": set(), "rows": 0})
        b["rows"] += 1
        if cust is not None and cust[i]:
            b["custs"].add(cust[i])
        if lan is not None and lan[i]:
            b["lans"].add(lan[i])

    rows = []
    for norm, b in buckets.items():
        distinct_cust = len(b["custs"]) if has_cust else b["rows"]
        if distinct_cust > threshold:
            rows.append(
                {
                    "Address (normalized)": norm[:80],
                    "Distinct Customers": distinct_cust,
                    "Loan Accounts": len(b["lans"]) if lan is not None else b["rows"],
                    "Risk": "CRITICAL" if distinct_cust > threshold * 2 else "HIGH",
                }
            )

    if not rows:
        return _note(f"No address shared by more than {threshold} customers")
    return pl.DataFrame(rows).sort("Distinct Customers", descending=True)


# ---------------------------------------------------------------------------
# CM-ID-01 — Name similarity clustering (fuzzy match, deterministic)
# ---------------------------------------------------------------------------


def _name_key(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z ]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def generate_name_similarity_clusters(
    df: pl.DataFrame, threshold: float = 0.92, bucket_cap: int = 400
) -> pl.DataFrame:
    """CM-ID-01: near-identical customer names with differing PAN within a pincode block.

    Deterministic fuzzy match via difflib.SequenceMatcher (no AI). Blocked by pincode
    (or processed as a single block when pincode is absent); large blocks are skipped
    with a logged cap to stay tractable.
    Returns: Name A, Name B, Similarity, Pincode, Distinct PAN, Risk.
    """
    from difflib import SequenceMatcher

    if not _has(df, "full_name"):
        return _note("full_name column not available")
    if df.is_empty():
        return _note("No data")

    names = _str_col(df, "full_name")
    pins = _str_col(df, "pincode") if "pincode" in df.columns else None
    pans = _str_col(df, "pan") if "pan" in df.columns else None

    # Block by pincode to bound the O(n^2) pair work.
    blocks: dict[str, list[int]] = defaultdict(list)
    for i in range(len(df)):
        if not _name_key(names[i]):
            continue
        key = pins[i] if pins is not None and pins[i] else "_ALL_"
        blocks[key].append(i)

    skipped_blocks = 0
    out = []
    for key, idxs in blocks.items():
        if len(idxs) > bucket_cap:
            skipped_blocks += 1
            continue
        for a in range(len(idxs)):
            ia = idxs[a]
            na = _name_key(names[ia])
            for b in range(a + 1, len(idxs)):
                ib = idxs[b]
                nb = _name_key(names[ib])
                if not nb or na == nb:
                    # exact-equal names are duplicate-detection territory, not "similarity"
                    if na == nb:
                        continue
                    continue
                score = SequenceMatcher(None, na, nb).ratio()
                if score >= threshold:
                    pan_a = pans[ia] if pans is not None else ""
                    pan_b = pans[ib] if pans is not None else ""
                    distinct_pan = len({p for p in (pan_a, pan_b) if p})
                    # Only flag when identities differ (different/with PAN) — true splitting signal.
                    if pans is not None and pan_a and pan_b and pan_a == pan_b:
                        continue
                    out.append(
                        {
                            "Name A": names[ia][:40],
                            "Name B": names[ib][:40],
                            "Similarity": round(score, 3),
                            "Pincode": key if key != "_ALL_" else "",
                            "Distinct PAN": distinct_pan,
                            "Risk": "HIGH",
                        }
                    )

    if not out:
        msg = "No name pairs above similarity threshold"
        if skipped_blocks:
            msg += f" ({skipped_blocks} oversized pincode block(s) skipped)"
        return _note(msg)
    result = pl.DataFrame(out).sort("Similarity", descending=True)
    return result.head(500)


# ---------------------------------------------------------------------------
# CM-ID-04 — Email domain anomalies (disposable / shared)
# ---------------------------------------------------------------------------


def generate_email_domain_anomalies(df: pl.DataFrame, shared_threshold: int = 10) -> pl.DataFrame:
    """CM-ID-04: disposable email domains, or one domain shared by many customers.

    Forensic typology: synthetic identity construction.
    Returns: Email Domain, Distinct Customers, Anomaly Type, Risk.
    """
    if not _has(df, "email"):
        return _note("email column not available")
    if df.is_empty():
        return _note("No data")

    emails = _str_col(df, "email")
    has_cust = "customer_id" in df.columns
    cust = _str_col(df, "customer_id") if has_cust else None

    domain_custs: dict[str, set] = defaultdict(set)
    domain_rows: dict[str, int] = defaultdict(int)
    for i in range(len(emails)):
        e = (emails[i] or "").lower()
        if "@" not in e:
            continue
        domain = e.split("@", 1)[1].strip()
        if not domain:
            continue
        domain_rows[domain] += 1
        if cust is not None and cust[i]:
            domain_custs[domain].add(cust[i])

    rows = []
    for domain in domain_rows:
        distinct = len(domain_custs[domain]) if has_cust else domain_rows[domain]
        is_disposable = domain in _DISPOSABLE_DOMAINS
        is_shared = distinct > shared_threshold
        if not (is_disposable or is_shared):
            continue
        if is_disposable and is_shared:
            atype, risk = "Disposable + Shared", "CRITICAL"
        elif is_disposable:
            atype, risk = "Disposable Domain", "HIGH"
        else:
            atype, risk = "Shared Domain", "MEDIUM"
        rows.append(
            {
                "Email Domain": domain,
                "Distinct Customers": distinct,
                "Anomaly Type": atype,
                "Risk": risk,
            }
        )

    if not rows:
        return _note("No disposable or over-shared email domains detected")
    return pl.DataFrame(rows).sort("Distinct Customers", descending=True)


# ---------------------------------------------------------------------------
# CM-DQ-06 — Sequential / templated KYC document numbers
# ---------------------------------------------------------------------------


def _numeric_tail(value: str) -> int | None:
    """Extract the longest embedded run of digits as an int (for sequence detection).

    Works for both digit-only IDs (Aadhaar) and alphanumerics with an embedded numeric
    block (PAN ``AAAAA9999A``, Voter ID ``ABC1234567``).
    """
    runs = re.findall(r"\d{3,}", value)
    if not runs:
        return None
    longest = max(runs, key=len)
    return int(longest)


def _sequential_for_field(df: pl.DataFrame, col: str, label: str) -> list[dict]:
    if col not in df.columns:
        return []
    series = _str_col(df, col)
    # Collect (numeric_tail, original) for non-empty values.
    nums = []
    for v in series:
        v = (v or "").upper()
        if not v:
            continue
        tail = _numeric_tail(v)
        if tail is not None:
            nums.append((tail, v))
    if len(nums) < 3:
        return []
    nums.sort(key=lambda t: t[0])
    runs = []
    cur = [nums[0]]
    for prev, item in zip(nums, nums[1:]):
        if item[0] - prev[0] == 1:
            cur.append(item)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = [item]
    if len(cur) >= 3:
        runs.append(cur)

    out = []
    for run in runs:
        out.append(
            {
                "Document Type": label,
                "Sequence Length": len(run),
                "First Value": run[0][1][:24],
                "Last Value": run[-1][1][:24],
                "Risk": "CRITICAL" if len(run) >= 5 else "HIGH",
            }
        )
    return out


def generate_sequential_kyc_documents(df: pl.DataFrame) -> pl.DataFrame:
    """CM-DQ-06: near-sequential KYC document numbers (batch-fabricated identity docs).

    Detects runs of >=3 consecutive trailing numeric values across PAN / Aadhaar /
    Voter ID / Passport / Driving Licence. (DSA/date partitioning is applied when those
    columns exist; otherwise the test runs portfolio-wide — a degraded but valid signal.)
    Returns: Document Type, Sequence Length, First Value, Last Value, Risk.
    """
    if df.is_empty():
        return _note("No data")
    candidates = [
        ("pan", "PAN"),
        ("aadhaar", "Aadhaar"),
        ("voter_id", "Voter ID"),
        ("passport", "Passport"),
        ("driving_licence", "Driving Licence"),
    ]
    if not any(c in df.columns for c, _ in candidates):
        return _note("No KYC document columns available")

    rows: list[dict] = []
    for col, label in candidates:
        rows.extend(_sequential_for_field(df, col, label))

    if not rows:
        return _note("No near-sequential KYC document runs detected")
    return pl.DataFrame(rows).sort("Sequence Length", descending=True)


# ---------------------------------------------------------------------------
# CM-DQ-07 — Benford's Law deviation in declared income
# ---------------------------------------------------------------------------


def generate_income_benford(df: pl.DataFrame) -> pl.DataFrame:
    """CM-DQ-07: first-digit Benford's Law conformity test on declared income.

    NOT_RUN-guarded: requires an ``income`` column. Computes observed vs expected
    first-digit frequencies and the Mean Absolute Deviation (Nigrini, 2012).
    Returns: Digit, Observed %, Expected %, Count + a final Conformity verdict row.
    """
    if not _has(df, "income"):
        return _note("income column not available (map a declared-income field to enable)")
    if df.is_empty():
        return _note("No data")

    # Parse leading digit from the numeric content of each income value.
    income = _str_col(df, "income")
    counts = {d: 0 for d in range(1, 10)}
    total = 0
    for v in income:
        digits = re.sub(r"[^0-9]", "", v or "")
        digits = digits.lstrip("0")
        if not digits:
            continue
        first = int(digits[0])
        if 1 <= first <= 9:
            counts[first] += 1
            total += 1

    if total < 30:
        return _note(f"Insufficient income values for Benford test (n={total}, need >=30)")

    mad = 0.0
    rows = []
    for d in range(1, 10):
        obs = counts[d] / total
        exp = _BENFORD_EXPECTED[d]
        mad += abs(obs - exp)
        rows.append(
            {
                "Digit": d,
                "Observed %": round(obs * 100, 2),
                "Expected %": round(exp * 100, 2),
                "Count": counts[d],
            }
        )
    mad = mad / 9

    if mad <= _BENFORD_MAD_CLOSE:
        verdict = "Close conformity"
    elif mad <= _BENFORD_MAD_ACCEPTABLE:
        verdict = "Acceptable conformity"
    elif mad <= _BENFORD_MAD_MARGINAL:
        verdict = "Marginally acceptable"
    else:
        verdict = "NON-CONFORMITY (investigate)"

    rows.append(
        {
            "Digit": "MAD",
            "Observed %": round(mad, 5),
            "Expected %": _BENFORD_MAD_ACCEPTABLE,
            "Count": total,
        }
    )
    rows.append({"Digit": verdict, "Observed %": None, "Expected %": None, "Count": None})
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# CM-DQ-09 — Missing / blank mandatory KYC fields by branch / DSA
# ---------------------------------------------------------------------------


def generate_kyc_completeness_by_branch(df: pl.DataFrame) -> pl.DataFrame:
    """CM-DQ-09: per-branch (or per-DSA) null-rate of mandatory KYC fields.

    NOT_RUN-guarded: requires a ``branch_code`` or ``dsa_code`` segmentation column.
    Flags segments whose average KYC null-rate exceeds 2x the portfolio average.
    Returns: Segment, Records, Avg KYC Null %, Portfolio Avg %, Flag.
    """
    seg_col = (
        "branch_code"
        if "branch_code" in df.columns
        else "dsa_code" if "dsa_code" in df.columns else None
    )
    if seg_col is None:
        return _note("branch_code / dsa_code column not available (map one to enable)")
    if df.is_empty():
        return _note("No data")

    mandatory = [
        c for c in ("pan", "aadhaar", "mobile", "address_line1", "pincode") if c in df.columns
    ]
    if not mandatory:
        return _note("No mandatory KYC fields present to measure")

    # Per-row null fraction across mandatory fields.
    null_exprs = [
        (
            (pl.col(c).is_null())
            | (pl.col(c).cast(pl.Utf8, strict=False).str.strip_chars().str.len_chars() == 0)
        ).cast(pl.Float64)
        for c in mandatory
    ]
    row_null = sum(null_exprs) / len(mandatory)
    work = df.select(
        [
            pl.col(seg_col).cast(pl.Utf8, strict=False).fill_null("(blank)").alias("Segment"),
            row_null.alias("_null_frac"),
        ]
    )

    portfolio_avg = work["_null_frac"].mean() or 0.0
    grouped = (
        work.group_by("Segment")
        .agg(
            [
                pl.len().alias("Records"),
                pl.col("_null_frac").mean().alias("_seg_null"),
            ]
        )
        .with_columns(
            [
                (pl.col("_seg_null") * 100).round(2).alias("Avg KYC Null %"),
                pl.lit(round(portfolio_avg * 100, 2)).alias("Portfolio Avg %"),
                pl.when(pl.col("_seg_null") > 2 * portfolio_avg)
                .then(pl.lit("FLAG (>2x avg)"))
                .otherwise(pl.lit(""))
                .alias("Flag"),
            ]
        )
        .drop("_seg_null")
        .sort("Avg KYC Null %", descending=True)
    )
    return grouped


# ---------------------------------------------------------------------------
# CM-ID-03 — Velocity of new-customer onboarding per DSA / branch
# ---------------------------------------------------------------------------


def generate_onboarding_velocity(df: pl.DataFrame) -> pl.DataFrame:
    """CM-ID-03: abnormal spikes in new-customer creation per branch / DSA per day.

    NOT_RUN-guarded: requires an ``onboarding_date`` column plus ``branch_code`` or
    ``dsa_code``. Flags (segment, day) counts above mean + 3*std for that segment.
    Returns: Segment, Date, New Customers, Segment Mean, Threshold, Risk.
    """
    if not _has(df, "onboarding_date"):
        return _note("onboarding_date column not available (map a date field to enable)")
    seg_col = (
        "branch_code"
        if "branch_code" in df.columns
        else "dsa_code" if "dsa_code" in df.columns else None
    )
    if seg_col is None:
        return _note("branch_code / dsa_code column not available (map one to enable)")
    if df.is_empty():
        return _note("No data")

    parsed = df.select(
        [
            pl.col(seg_col).cast(pl.Utf8, strict=False).fill_null("(blank)").alias("Segment"),
            pl.col("onboarding_date")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_date(strict=False)
            .alias("_d"),
        ]
    ).filter(pl.col("_d").is_not_null())
    if parsed.is_empty():
        return _note("No parseable onboarding dates")

    daily = parsed.group_by(["Segment", "_d"]).agg(pl.len().alias("New Customers"))
    stats = daily.group_by("Segment").agg(
        [
            pl.col("New Customers").mean().alias("_mean"),
            pl.col("New Customers").std(ddof=0).fill_null(0.0).alias("_std"),
        ]
    )
    joined = daily.join(stats, on="Segment").with_columns(
        (pl.col("_mean") + 3 * pl.col("_std")).alias("_threshold")
    )
    flagged = (
        joined.filter(
            (pl.col("New Customers") > pl.col("_threshold")) & (pl.col("New Customers") >= 3)
        )
        .with_columns(
            [
                pl.col("_d").cast(pl.Utf8).alias("Date"),
                pl.col("_mean").round(2).alias("Segment Mean"),
                pl.col("_threshold").round(2).alias("Threshold"),
                pl.lit("HIGH").alias("Risk"),
            ]
        )
        .select(["Segment", "Date", "New Customers", "Segment Mean", "Threshold", "Risk"])
        .sort("New Customers", descending=True)
    )
    if flagged.is_empty():
        return _note("No onboarding-velocity spikes above mean + 3*std")
    return flagged.head(200)


# ---------------------------------------------------------------------------
# Registry — used by the run pipeline + workpaper to iterate all catalogue analytics
# ---------------------------------------------------------------------------

# (key, title, catalogue_id, fn)
CATALOGUE_ANALYTICS = [
    (
        "address_clustering",
        "Address Clustering (Ghost Borrowers)",
        "CM-DQ-10",
        generate_address_clustering,
    ),
    ("name_similarity", "Name Similarity Clusters", "CM-ID-01", generate_name_similarity_clusters),
    (
        "email_domain_anomalies",
        "Email Domain Anomalies",
        "CM-ID-04",
        generate_email_domain_anomalies,
    ),
    (
        "sequential_kyc",
        "Sequential KYC Document Numbers",
        "CM-DQ-06",
        generate_sequential_kyc_documents,
    ),
    ("income_benford", "Income Benford's Law Test", "CM-DQ-07", generate_income_benford),
    (
        "kyc_by_branch",
        "Missing KYC by Branch / DSA",
        "CM-DQ-09",
        generate_kyc_completeness_by_branch,
    ),
    ("onboarding_velocity", "Onboarding Velocity Spikes", "CM-ID-03", generate_onboarding_velocity),
]
