"""Customer Master summary analytics — statutory audit requirements.

Operates on a Polars DataFrame of all customer master records for an engagement.
All compute functions are pure Polars (vectorised, no Python loops).
Missing columns are skipped gracefully.
"""

from __future__ import annotations

import polars as pl

# ---------------------------------------------------------------------------
# 1. Geographic distribution
# ---------------------------------------------------------------------------


def generate_geographic_distribution(df: pl.DataFrame) -> pl.DataFrame:
    """Summarise customers by state and district.

    Returns: state, district, customer_count
    """
    if "state" not in df.columns:
        return pl.DataFrame({"note": ["state column not available"]})

    group_cols = ["state"]
    if "district" in df.columns:
        group_cols.append("district")

    select_cols = group_cols.copy()
    if "customer_id" in df.columns:
        select_cols.append("customer_id")
        agg = [pl.col("customer_id").n_unique().alias("Customer Count")]
    else:
        agg = [pl.len().alias("Record Count")]

    result = (
        df.select(select_cols)
        .filter(pl.col("state").is_not_null())
        .group_by(group_cols)
        .agg(agg)
        .sort(group_cols)
    )

    return result


# ---------------------------------------------------------------------------
# 2. KYC field completeness
# ---------------------------------------------------------------------------


def generate_kyc_completeness(df: pl.DataFrame) -> pl.DataFrame:
    """% present for each KYC ID field type.

    Returns: field, present_count, missing_count, percent_present
    """
    id_fields = [
        "pan",
        "aadhaar",
        "voter_id",
        "passport",
        "driving_licence",
        "mobile",
        "email",
        "dob",
    ]

    total_rows = len(df)
    if total_rows == 0:
        return pl.DataFrame({"note": ["No data"]})

    results = []
    for field in id_fields:
        if field not in df.columns:
            continue
        present = (
            df.select(pl.col(field))
            .filter(pl.col(field).is_not_null())
            .filter(pl.col(field).cast(pl.Utf8, strict=False).str.lengths() > 0)
            .len()
        )
        missing = total_rows - present
        pct = (present / total_rows * 100) if total_rows > 0 else 0
        results.append(
            {
                "Field": field.replace("_", " ").title(),
                "Present": present,
                "Missing": missing,
                "Percent Present": round(pct, 2),
            }
        )

    if not results:
        return pl.DataFrame({"note": ["No ID fields found"]})

    return pl.DataFrame(results)


# ---------------------------------------------------------------------------
# 3. Demographic distribution
# ---------------------------------------------------------------------------


def generate_demographic_distribution(df: pl.DataFrame) -> pl.DataFrame:
    """Age buckets and gender distribution; flag implausible ages.

    Returns: age_bucket, gender, count
    """
    if "dob" not in df.columns:
        return pl.DataFrame({"note": ["dob column not available"]})

    from datetime import datetime

    today = datetime.now()

    def calculate_age(dob_str):
        if not dob_str or str(dob_str).strip() == "":
            return None
        try:
            dob = pl.Series([dob_str]).str.to_date("%d-%m-%Y").item()
            if dob is None:
                return None
            age = (today.date() - dob).days // 365
            return age if 0 <= age <= 120 else None
        except Exception:
            return None

    df_with_age = df.with_columns(
        pl.col("dob").map_elements(calculate_age, return_dtype=pl.Int32).alias("age")
    )

    df_filtered = df_with_age.filter(pl.col("age").is_not_null())

    if df_filtered.is_empty():
        return pl.DataFrame({"note": ["No valid DOBs found"]})

    # Create age buckets
    df_bucketed = df_filtered.with_columns(
        pl.when(pl.col("age") < 26)
        .then(pl.lit("18-25"))
        .when(pl.col("age") < 36)
        .then(pl.lit("26-35"))
        .when(pl.col("age") < 51)
        .then(pl.lit("36-50"))
        .when(pl.col("age") < 66)
        .then(pl.lit("51-65"))
        .otherwise(pl.lit("65+"))
        .alias("age_bucket")
    )

    group_cols = ["age_bucket"]
    if "gender" in df_bucketed.columns:
        group_cols.append("gender")

    if "customer_id" in df_bucketed.columns:
        agg = [pl.col("customer_id").n_unique().alias("Count")]
    else:
        agg = [pl.len().alias("Count")]

    result = df_bucketed.group_by(group_cols).agg(agg).sort(group_cols)

    return result


# ---------------------------------------------------------------------------
# 4. Duplication summary
# ---------------------------------------------------------------------------


def generate_duplication_summary(df: pl.DataFrame) -> pl.DataFrame:
    """Count each duplicate type from rule outputs (via long CSV aggregation).

    For now, returns a note — in practice, this aggregates from the long CSV
    exception rows where rule_id in (pan_duplicate, aadhaar_duplicate, ...).
    """
    duplicate_rules = [
        "pan_duplicate",
        "aadhaar_duplicate",
        "mobile_duplicate",
        "bank_account_duplicate",
        "name_dob_duplicate",
        "voter_id_duplicate",
        "address_duplicate",
    ]

    # If the dataframe has rule_id column (from long CSV), aggregate
    if "rule_id" not in df.columns:
        return pl.DataFrame(
            {
                "Duplicate Type": duplicate_rules,
                "Count": [0] * len(duplicate_rules),
            }
        )

    results = []
    for dup_rule in duplicate_rules:
        count = df.filter((pl.col("rule_id") == dup_rule) & (pl.col("status") == "ERROR")).len()
        results.append(
            {
                "Duplicate Type": dup_rule.replace("_", " ").title(),
                "Count": count,
            }
        )

    return pl.DataFrame(results)


# ---------------------------------------------------------------------------
# 5. Co-applicant overlap
# ---------------------------------------------------------------------------


def generate_coapplicant_overlap(df: pl.DataFrame) -> pl.DataFrame:
    """Count customers where coapplicant_mobile matches any applicant mobile.

    Returns: overlap_status, count
    """
    if "mobile" not in df.columns or "coapplicant_mobile" not in df.columns:
        return pl.DataFrame({"note": ["mobile and/or coapplicant_mobile not available"]})

    mobile_set = set(
        df.select(pl.col("mobile")).filter(pl.col("mobile").is_not_null()).to_series().to_list()
    )

    overlap_count = df.filter(
        pl.col("coapplicant_mobile").is_not_null()
        & pl.col("coapplicant_mobile").map_elements(
            lambda x: x in mobile_set, return_dtype=pl.Boolean
        )
    ).len()

    no_overlap_count = len(df) - overlap_count

    return pl.DataFrame(
        {
            "Overlap Status": ["Co-applicant mobile matches", "No match"],
            "Count": [overlap_count, no_overlap_count],
        }
    )


# ---------------------------------------------------------------------------
# 6. Related-party clusters (by UCID group size)
# ---------------------------------------------------------------------------


def generate_cluster_distribution(df: pl.DataFrame) -> pl.DataFrame:
    """Group size distribution: how many customers in clusters of size 1, 2–5, 6–10, 10+.

    Uses ucid_size column (emitted by the ucid rule).
    """
    if "ucid_size" not in df.columns:
        return pl.DataFrame({"note": ["ucid_size column not available (run UCID rule first)"]})

    df_valid = df.filter(pl.col("ucid_size").is_not_null())

    if df_valid.is_empty():
        return pl.DataFrame({"note": ["No UCID groups found"]})

    def bucket_size(size):
        if size <= 1:
            return "1 (Solo)"
        elif size <= 5:
            return "2-5"
        elif size <= 10:
            return "6-10"
        else:
            return "10+"

    df_bucketed = df_valid.with_columns(
        pl.col("ucid_size")
        .map_elements(bucket_size, return_dtype=pl.Utf8)
        .alias("cluster_size_band")
    )

    if "customer_id" in df_bucketed.columns:
        agg = [pl.col("customer_id").n_unique().alias("Customers in Band")]
    else:
        agg = [pl.len().alias("Customers in Band")]

    result = (
        df_bucketed.group_by("cluster_size_band")
        .agg(agg)
        .with_columns(pl.col("Customers in Band").sum().alias("Total Customers"))
        .sort("cluster_size_band")
    )

    return result


# ---------------------------------------------------------------------------
# 7. Data-quality summary
# ---------------------------------------------------------------------------


def generate_data_quality_summary(df: pl.DataFrame) -> pl.DataFrame:
    """Missing rate (%) per column across all rows.

    Returns: column_name, present_count, missing_count, percent_missing
    """
    canonical_cols = [
        "customer_id",
        "full_name",
        "dob",
        "gender",
        "mobile",
        "email",
        "pan",
        "aadhaar",
        "voter_id",
        "passport",
        "driving_licence",
        "address_line1",
        "address_line2",
        "city",
        "district",
        "state",
        "pincode",
        "bank_account",
        "ifsc",
        "lan",
    ]

    total_rows = len(df)
    if total_rows == 0:
        return pl.DataFrame({"note": ["No data"]})

    results = []
    for col in canonical_cols:
        if col not in df.columns:
            continue
        present = (
            df.select(pl.col(col))
            .filter(pl.col(col).is_not_null())
            .filter(pl.col(col).cast(pl.Utf8, strict=False).str.lengths() > 0)
            .len()
        )
        missing = total_rows - present
        pct_missing = (missing / total_rows * 100) if total_rows > 0 else 0
        results.append(
            {
                "Column": col.replace("_", " ").title(),
                "Present": present,
                "Missing": missing,
                "Percent Missing": round(pct_missing, 2),
            }
        )

    if not results:
        return pl.DataFrame({"note": ["No columns found"]})

    return pl.DataFrame(results).sort("Percent Missing", descending=True)


# ---------------------------------------------------------------------------
# 8. LAN concentration (top-N customers by distinct loans)
# ---------------------------------------------------------------------------


def generate_lan_concentration(df: pl.DataFrame, top_n: int = 10) -> pl.DataFrame:
    """Top-N customers by distinct loan accounts.

    Returns: rank, customer_id, distinct_lans, ucid
    """
    if "lan" not in df.columns or "customer_id" not in df.columns:
        return pl.DataFrame({"note": ["lan and/or customer_id not available"]})

    group_cols = ["customer_id"]
    if "ucid" in df.columns:
        group_cols.append("ucid")

    result = (
        df.group_by(group_cols)
        .agg(pl.col("lan").n_unique().alias("Distinct LANs"))
        .sort("Distinct LANs", descending=True)
        .head(top_n)
        .with_columns(pl.int_range(1, pl.len() + 1).alias("Rank"))
        .select(
            ["Rank", "customer_id", "Distinct LANs"] + (["ucid"] if "ucid" in group_cols else [])
        )
    )

    return result
