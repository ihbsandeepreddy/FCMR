"""EAD Statutory-Audit Summary Reports — pure-Polars analytics.

8 summary reports designed for audit workpapers (concentration, coverage, risk, quality).
Missing columns handled gracefully (returns "note" dataframe).
"""

from __future__ import annotations

import polars as pl


def generate_portfolio_concentration(df: pl.DataFrame, top_n: int = 10) -> pl.DataFrame:
    """Portfolio concentration: top products, regions, and customers by EAD/exposure."""
    if "loan_id" not in df.columns or "ead" not in df.columns:
        return pl.DataFrame({"note": ["ead and loan_id columns required"]})

    # Top 10 customers (by count of loans and sum of EAD)
    top_customers = (
        df.group_by("loan_id")
        .agg(
            pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"),
            pl.col("loan_id").count().alias("Loan Count"),
        )
        .sort("Total EAD", descending=True)
        .head(top_n)
        .with_columns(pl.int_range(1, pl.len() + 1).alias("Rank"))
        .select(["Rank", "loan_id", "Total EAD", "Loan Count"])
    )

    return top_customers


def generate_stage_distribution(df: pl.DataFrame) -> pl.DataFrame:
    """Stage distribution: count and EAD by Ind AS 109 stage."""
    if "stage" not in df.columns:
        return pl.DataFrame({"note": ["stage column required"]})

    result = (
        df.group_by("stage")
        .agg(
            pl.col("loan_id").n_unique().alias("Loan Count"),
            pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"),
        )
        .sort("Total EAD", descending=True)
    )

    return result if not result.is_empty() else pl.DataFrame({"note": ["No stage data"]})


def generate_dpd_risk_distribution(df: pl.DataFrame) -> pl.DataFrame:
    """DPD/risk distribution: healthy, stressed, and NPA buckets."""
    if "dpd_bucket" not in df.columns:
        return pl.DataFrame({"note": ["dpd_bucket column required"]})

    result = (
        df.group_by("dpd_bucket")
        .agg(
            pl.col("loan_id").n_unique().alias("Loan Count"),
            pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"),
        )
        .sort("Total EAD", descending=True)
    )

    return result if not result.is_empty() else pl.DataFrame({"note": ["No DPD data"]})


def generate_collateral_coverage(df: pl.DataFrame) -> pl.DataFrame:
    """Collateral coverage: covered vs uncovered portion analysis."""
    if "collateral_value" not in df.columns or "ead" not in df.columns:
        return pl.DataFrame({"note": ["collateral_value and ead columns required"]})

    total_ead = df.select(pl.col("ead").cast(pl.Float64, strict=False).sum())[0, 0] or 0
    covered = (
        df.filter(pl.col("collateral_value").is_not_null()).select(
            pl.col("collateral_value").cast(pl.Float64, strict=False).sum()
        )[0, 0]
        or 0
    )
    uncovered = total_ead - covered

    pct_covered = (covered / total_ead * 100) if total_ead > 0 else 0

    return pl.DataFrame(
        {
            "Coverage Type": ["Covered", "Uncovered", "Total"],
            "Amount": [covered, uncovered, total_ead],
            "Percent": [
                round(pct_covered, 2),
                round(100 - pct_covered, 2),
                100.0,
            ],
        }
    )


def generate_provision_coverage(df: pl.DataFrame) -> pl.DataFrame:
    """Provision coverage: provided amount vs exposure by stage."""
    if "total_provision" not in df.columns or "ead" not in df.columns:
        return pl.DataFrame({"note": ["total_provision and ead columns required"]})

    total_ead = df.select(pl.col("ead").cast(pl.Float64, strict=False).sum())[0, 0] or 0
    total_provision = (
        df.select(pl.col("total_provision").cast(pl.Float64, strict=False).sum())[0, 0] or 0
    )

    pct_provided = (total_provision / total_ead * 100) if total_ead > 0 else 0
    uncovered = total_ead - total_provision

    return pl.DataFrame(
        {
            "Coverage Type": ["Provided", "Uncovered", "Total Exposure"],
            "Amount": [total_provision, uncovered, total_ead],
            "Percent": [
                round(pct_provided, 2),
                round(100 - pct_provided, 2),
                100.0,
            ],
        }
    )


def generate_writeoff_recovery(df: pl.DataFrame) -> pl.DataFrame:
    """Write-off and recovery summary: count and amount by status."""
    if "written_off" not in df.columns:
        return pl.DataFrame({"note": ["written_off column required"]})

    result = (
        df.group_by("written_off")
        .agg(
            pl.col("loan_id").n_unique().alias("Loan Count"),
            pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"),
        )
        .sort("Total EAD", descending=True)
    )

    return result if not result.is_empty() else pl.DataFrame({"note": ["No write-off data"]})


def generate_sanction_disbursement_variance(df: pl.DataFrame) -> pl.DataFrame:
    """Sanction vs disbursement: variance analysis (drawn % of sanctioned)."""
    if "sanction_amount" not in df.columns or "disbursed_amount" not in df.columns:
        return pl.DataFrame({"note": ["sanction_amount and disbursed_amount columns required"]})

    total_sanction = (
        df.filter(pl.col("sanction_amount").is_not_null()).select(
            pl.col("sanction_amount").cast(pl.Float64, strict=False).sum()
        )[0, 0]
        or 0
    )
    total_disbursed = (
        df.filter(pl.col("disbursed_amount").is_not_null()).select(
            pl.col("disbursed_amount").cast(pl.Float64, strict=False).sum()
        )[0, 0]
        or 0
    )

    pct_drawn = (total_disbursed / total_sanction * 100) if total_sanction > 0 else 0
    undrawn = total_sanction - total_disbursed

    return pl.DataFrame(
        {
            "Amount Type": ["Sanctioned", "Disbursed", "Undrawn"],
            "Amount": [total_sanction, total_disbursed, undrawn],
            "Percent": [100.0, round(pct_drawn, 2), round(100 - pct_drawn, 2)],
        }
    )


def generate_data_quality_summary_ead(df: pl.DataFrame) -> pl.DataFrame:
    """Data quality summary: missing rate per key EAD column."""
    canonical_cols = [
        "loan_id",
        "stage",
        "dpd_bucket",
        "ead",
        "gross_book_value",
        "outstanding_principal",
        "collateral_value",
        "total_provision",
        "written_off",
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
            .filter(pl.col(col).cast(pl.Utf8, strict=False).str.len_chars() > 0)
            .height
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
