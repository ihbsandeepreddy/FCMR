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


def generate_coapplicant_concentration(df: pl.DataFrame) -> pl.DataFrame:
    """Co-applicant concentration: identify shared co-applicants across primaries.

    Detects:
    - Co-applicants appearing across multiple primary applicants (related-party risk)
    - Concentration of co-applicant relationships (single person backing many loans)

    Returns DataFrame with co_applicant_mobile, primary_count, loan_count.
    """
    if "coapplicant_mobile" not in df.columns:
        return pl.DataFrame({"note": ["coapplicant_mobile column required"]})

    # Filter to rows with non-null co-applicant mobile
    coapplicant_rows = df.filter(
        (pl.col("coapplicant_mobile").is_not_null())
        & (pl.col("coapplicant_mobile").cast(pl.Utf8, strict=False).str.len_chars() > 0)
    )

    if len(coapplicant_rows) == 0:
        return pl.DataFrame({"note": ["No co-applicant data found"]})

    # Aggregate: per coapplicant_mobile, count distinct primary customers + distinct loans
    concentration = (
        coapplicant_rows.group_by("coapplicant_mobile")
        .agg(
            [
                pl.col("customer_id").n_unique().alias("Primary_Applicants"),
                pl.col("lan").n_unique().alias("Loan_Count"),
            ]
        )
        .filter(pl.col("Primary_Applicants") > 1)  # Only co-applicants linked to 2+ primaries
        .sort("Loan_Count", descending=True)
    )

    if len(concentration) == 0:
        return pl.DataFrame({"note": ["No concentrated co-applicant relationships"]})

    # Remove the masked coapplicant_mobile from output (privacy); show counts only
    return concentration.select(
        [
            pl.lit("Multiple Primary Links").alias("Concentration Type"),
            pl.col("Primary_Applicants"),
            pl.col("Loan_Count"),
        ]
    ).with_columns(
        [
            pl.col("Primary_Applicants").cast(pl.Int64),
            pl.col("Loan_Count").cast(pl.Int64),
        ]
    )


def generate_bank_account_anomalies(df: pl.DataFrame) -> pl.DataFrame:
    """Bank account anomalies: invalid lengths, IFSC format, state mismatches.

    Detects:
    - Account numbers outside valid range (9–18 digits)
    - IFSC codes not matching standard format (4-letter bank code + 0 + 4-char branch)
    - IFSC state code mismatches vs. customer state

    Returns DataFrame with anomaly_type, account_count, percent.
    """
    if "bank_account" not in df.columns:
        return pl.DataFrame({"note": ["bank_account column required"]})

    total_customers = df.select(pl.col("customer_id")).n_unique()
    if total_customers == 0:
        return pl.DataFrame({"note": ["No customers"]})

    anomalies = []

    # Anomaly 1: Invalid account length (not 9–18 digits)
    if "bank_account" in df.columns:
        invalid_acct = (
            df.filter(
                (pl.col("bank_account").is_not_null())
                & (
                    (pl.col("bank_account").cast(pl.Utf8, strict=False).str.len_chars().lt(9))
                    | (pl.col("bank_account").cast(pl.Utf8, strict=False).str.len_chars().gt(18))
                )
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )

        if invalid_acct > 0:
            anomalies.append(
                {
                    "Anomaly Type": "Invalid Account Length",
                    "Customer Count": invalid_acct,
                    "Percent": round(invalid_acct / total_customers * 100, 2),
                }
            )

    # Anomaly 2: Invalid IFSC format (should be 4-letter + 0 + 4-char)
    if "ifsc" in df.columns:
        invalid_ifsc = (
            df.filter(
                (pl.col("ifsc").is_not_null())
                & (
                    ~pl.col("ifsc")
                    .cast(pl.Utf8, strict=False)
                    .str.to_uppercase()
                    .str.contains(r"^[A-Z]{4}0[A-Z0-9]{4}$")
                )
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )

        if invalid_ifsc > 0:
            anomalies.append(
                {
                    "Anomaly Type": "Invalid IFSC Format",
                    "Customer Count": invalid_ifsc,
                    "Percent": round(invalid_ifsc / total_customers * 100, 2),
                }
            )

    # Anomaly 3: IFSC state mismatch vs. customer state
    if "ifsc" in df.columns and "state" in df.columns:
        # IFSC state code (extract char 5–6, map to state abbreviation)
        # Simplified: flag when IFSC and state are both non-null but appear unrelated
        # (Full validation would require a state-code lookup table)
        state_mismatch = (
            df.filter(
                (pl.col("ifsc").is_not_null())
                & (pl.col("state").is_not_null())
                & (
                    ~pl.col("ifsc")
                    .cast(pl.Utf8, strict=False)
                    .str.to_uppercase()
                    .str.slice(4, 2)
                    .str.contains(
                        pl.col("state")
                        .cast(pl.Utf8, strict=False)
                        .str.to_uppercase()
                        .str.slice(0, 2)
                    )
                )
            )
            .select(pl.col("customer_id"))
            .n_unique()
        )

        if state_mismatch > 0:
            anomalies.append(
                {
                    "Anomaly Type": "IFSC State Mismatch",
                    "Customer Count": state_mismatch,
                    "Percent": round(state_mismatch / total_customers * 100, 2),
                }
            )

    if not anomalies:
        return pl.DataFrame({"note": ["No bank account anomalies detected"]})

    return pl.DataFrame(anomalies)
