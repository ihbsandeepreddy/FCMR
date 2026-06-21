"""CM Best-Practice Analytics — audit-focused compliance and risk reports.

Pure Polars, missing-column-safe. Complements the 31-rule pipeline and 8 summary reports.
"""

from __future__ import annotations

import polars as pl


def generate_aadhaar_coverage(df: pl.DataFrame) -> pl.DataFrame:
    """Aadhaar coverage: % of portfolio with Aadhaar (KYC compliance mandate).

    Returns a single-row DataFrame with coverage metrics.
    """
    if "aadhaar" not in df.columns:
        return pl.DataFrame({"note": ["aadhaar column required"]})

    total_rows = len(df)
    if total_rows == 0:
        return pl.DataFrame({"note": ["No data"]})

    # Count non-null Aadhaar values
    aadhaar_present = (
        df.select(pl.col("aadhaar"))
        .filter(pl.col("aadhaar").is_not_null())
        .filter(pl.col("aadhaar").cast(pl.Utf8, strict=False).str.len_chars() > 0)
        .height
    )
    aadhaar_missing = total_rows - aadhaar_present
    coverage_pct = (aadhaar_present / total_rows * 100) if total_rows > 0 else 0

    return pl.DataFrame(
        {
            "Coverage Status": ["Present", "Missing", "Total"],
            "Count": [aadhaar_present, aadhaar_missing, total_rows],
            "Percent": [
                round(coverage_pct, 2),
                round(100 - coverage_pct, 2),
                100.0,
            ],
        }
    )


def generate_fraud_risk_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Fraud-risk flags: KYC consistency & identity-matching red flags.

    Identifies customers with:
    - Inconsistent UCID (same person, conflicting identity attributes)
    - Missing critical identity fields (PAN, Aadhaar, Mobile)
    - Multiple email/mobile per UCID (potential identity confusion)

    Returns DataFrame with customer, flag_type, flag_count.
    """
    required_cols = ["customer_id"]
    if not all(col in df.columns for col in required_cols):
        return pl.DataFrame({"note": ["customer_id column required"]})

    total_customers = df.select(pl.col("customer_id")).n_unique()
    if total_customers == 0:
        return pl.DataFrame({"note": ["No customers"]})

    flags = []

    # Flag 1: Customers with missing PAN (high-risk KYC)
    if "pan" in df.columns:
        pan_missing = (
            df.filter(
                (pl.col("pan").is_null())
                | (pl.col("pan").cast(pl.Utf8, strict=False).str.len_chars() == 0)
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )
        if pan_missing > 0:
            flags.append(
                {
                    "Risk Category": "Missing PAN",
                    "Customer Count": pan_missing,
                    "Percent": round(pan_missing / total_customers * 100, 2),
                }
            )

    # Flag 2: Customers with missing Aadhaar (compliance gap)
    if "aadhaar" in df.columns:
        aadhaar_missing = (
            df.filter(
                (pl.col("aadhaar").is_null())
                | (pl.col("aadhaar").cast(pl.Utf8, strict=False).str.len_chars() == 0)
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )
        if aadhaar_missing > 0:
            flags.append(
                {
                    "Risk Category": "Missing Aadhaar",
                    "Customer Count": aadhaar_missing,
                    "Percent": round(aadhaar_missing / total_customers * 100, 2),
                }
            )

    # Flag 3: Customers with missing Mobile (contact verification gap)
    if "mobile" in df.columns:
        mobile_missing = (
            df.filter(
                (pl.col("mobile").is_null())
                | (pl.col("mobile").cast(pl.Utf8, strict=False).str.len_chars() == 0)
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )
        if mobile_missing > 0:
            flags.append(
                {
                    "Risk Category": "Missing Mobile",
                    "Customer Count": mobile_missing,
                    "Percent": round(mobile_missing / total_customers * 100, 2),
                }
            )

    # Flag 4: Multiple distinct mobiles per customer (potential shared identity)
    if "mobile" in df.columns and "ucid" in df.columns:
        multi_mobile = (
            df.filter(pl.col("mobile").is_not_null())
            .group_by("customer_id")
            .agg(pl.col("mobile").n_unique().alias("mobile_count"))
            .filter(pl.col("mobile_count") > 1)
            .height
        )
        if multi_mobile > 0:
            flags.append(
                {
                    "Risk Category": "Multiple Mobiles per Customer",
                    "Customer Count": multi_mobile,
                    "Percent": round(multi_mobile / total_customers * 100, 2),
                }
            )

    # Flag 5: Multiple distinct emails per customer
    if "email" in df.columns:
        multi_email = (
            df.filter(pl.col("email").is_not_null())
            .group_by("customer_id")
            .agg(pl.col("email").n_unique().alias("email_count"))
            .filter(pl.col("email_count") > 1)
            .height
        )
        if multi_email > 0:
            flags.append(
                {
                    "Risk Category": "Multiple Emails per Customer",
                    "Customer Count": multi_email,
                    "Percent": round(multi_email / total_customers * 100, 2),
                }
            )

    if not flags:
        return pl.DataFrame({"note": ["No fraud-risk flags detected"]})

    return pl.DataFrame(flags)
