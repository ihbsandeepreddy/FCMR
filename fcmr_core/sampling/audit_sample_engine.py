"""Deterministic audit sampling engine for NBFC loan portfolios (10M scale)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

SEED = 42
MAX_PER_EXCEPTION = 10
TARGET_PCT = 0.005
TARGET_MIN = 50


def generate_synthetic_loan_master(n_rows: int = 10_000_000) -> pl.DataFrame:
    """Generate synthetic NBFC loan customer master."""
    random.seed(SEED)

    base_date = datetime(2019, 1, 1)
    n_products, n_branches, n_customers = 50, 200, int(n_rows * 0.7)

    dates = [
        (base_date + timedelta(days=random.randint(0, 365 * 5))).strftime("%Y-%m-%d")
        for _ in range(n_rows)
    ]

    return pl.DataFrame({
        "LAN": [f"LAN{i:010d}" for i in range(n_rows)],
        "CUSTOMER_ID": [f"CUST{random.randint(1000, n_customers):08d}" for _ in range(n_rows)],
        "LOAN_DATE": dates,
        "SANCTIONED_AMT": [random.randint(50000, 10000000) for _ in range(n_rows)],
        "OUTSTANDING_AMT": [random.randint(0, 9000000) for _ in range(n_rows)],
        "INTEREST_RATE": [round(random.uniform(5.5, 22.0), 2) for _ in range(n_rows)],
        "TENURE_MONTHS": [random.choice([12, 24, 36, 48, 60, 84]) for _ in range(n_rows)],
        "LOAN_STATUS": [random.choice(["Active", "Closed", "NPA", "Written-off"]) for _ in range(n_rows)],
        "DPD": [random.choice([0, 30, 60, 90, 180, 360]) for _ in range(n_rows)],
        "PRODUCT": [f"PROD{random.randint(1, n_products):03d}" for _ in range(n_rows)],
        "BRANCH": [f"BR{random.randint(1, n_branches):04d}" for _ in range(n_rows)],
        "KYC_STATUS": [random.choice(["Complete", "Expired", "Pending", "Missing"]) for _ in range(n_rows)],
    }).with_row_count("ROW_ID")


def detect_and_flag_exceptions(df: pl.DataFrame) -> pl.DataFrame:
    """Detect data quality / business rule exceptions."""
    # Flag invalid amounts
    has_amount_issue = (
        (df["SANCTIONED_AMT"].is_null()) |
        (df["SANCTIONED_AMT"] <= 0) |
        (df["OUTSTANDING_AMT"] > df["SANCTIONED_AMT"])
    )

    # Flag invalid rates/tenure
    has_rate_issue = (df["INTEREST_RATE"] <= 0) | (df["INTEREST_RATE"] > 25)
    has_tenure_issue = df["TENURE_MONTHS"] <= 0

    # Flag date issues
    has_kyc_issue = df["KYC_STATUS"].is_in(["Missing", "Expired", "Pending"])

    # Flag status mismatches
    has_status_issue = (
        (df["LOAN_STATUS"] == "Closed") & (df["OUTSTANDING_AMT"] > 0)
    ) | (
        (df["LOAN_STATUS"].is_in(["Written-off", "NPA"])) & (df["DPD"] == 0)
    )

    # Combine: any issue = exception
    has_exception = (
        has_amount_issue | has_rate_issue | has_tenure_issue |
        has_kyc_issue | has_status_issue
    )

    return df.with_columns(
        pl.when(has_exception).then(1).otherwise(0).alias("IS_EXCEPTION")
    )


def compute_recency_weight(df: pl.DataFrame) -> pl.DataFrame:
    """Compute recency weight (0.25-1.0) based on LOAN_DATE."""
    try:
        dates_ts = pl.Series([
            datetime.strptime(str(d), "%Y-%m-%d").timestamp()
            for d in df["LOAN_DATE"]
        ])
        min_ts, max_ts = dates_ts.min(), dates_ts.max()
        if max_ts == min_ts:
            weights = pl.Series([0.625] * len(df))
        else:
            normalized = (dates_ts - min_ts) / (max_ts - min_ts)
            weights = 0.25 + 0.75 * normalized
        return df.with_columns(weights.alias("RECENCY_WEIGHT"))
    except Exception:
        return df.with_columns(pl.lit(0.625).alias("RECENCY_WEIGHT"))


def run_audit_sampling(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Audit sampling: exceptions + strata + random."""
    n_pop = len(df)

    # Exception detection
    df = detect_and_flag_exceptions(df)
    df = compute_recency_weight(df)

    # Split
    df_exc = df.filter(pl.col("IS_EXCEPTION") == 1).sort("RECENCY_WEIGHT", descending=True)
    df_clean = df.filter(pl.col("IS_EXCEPTION") == 0)

    n_exceptions = len(df_exc)
    n_clean = len(df_clean)

    # Sample exceptions (max 10% of exceptions total, capped at 10 per class conceptually, but just take top recent)
    sample_exc = df_exc.head(max(10, min(100, n_exceptions // 10)))

    # Strata coverage
    strata = df_clean.group_by(["PRODUCT", "LOAN_STATUS", "BRANCH"]).head(1)
    n_strata = len(strata)

    # Random from remaining clean
    remaining_clean = df_clean.filter(~df_clean["ROW_ID"].is_in(strata["ROW_ID"]))
    target_random = max(int(n_clean * TARGET_PCT), TARGET_MIN) - n_strata
    target_random = max(0, target_random)

    if target_random > 0 and len(remaining_clean) > 0:
        random.seed(SEED)
        weights = remaining_clean["RECENCY_WEIGHT"].to_list()
        total_w = sum(weights)
        probs = [w / total_w for w in weights]
        indices = random.choices(range(len(remaining_clean)), weights=probs, k=min(target_random, len(remaining_clean)))
        sample_random = remaining_clean[indices]
    else:
        sample_random = pl.DataFrame()

    # Combine
    samples = [s for s in [sample_exc, strata, sample_random] if len(s) > 0]
    selected = pl.concat(samples, how="diagonal_relaxed") if samples else pl.DataFrame()

    summary = {
        "population_total": n_pop,
        "clean_records": n_clean,
        "exception_records": n_exceptions,
        "exceptions_sampled": len(sample_exc),
        "strata_coverage_sampled": n_strata,
        "random_sampled": len(sample_random),
        "total_sample_size": len(selected) if selected.height > 0 else 0,
        "sample_pct": (len(selected) / n_pop * 100) if n_pop > 0 else 0,
    }

    return selected, summary


def export_to_excel(sample: pl.DataFrame, summary: dict, output_path: Path) -> None:
    """Export to Excel."""
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws_sample = wb.active
        ws_sample.title = "Audit Sample"

        ws_summary = wb.create_sheet("Summary")

        # Sample sheet
        headers = sample.columns
        ws_sample.append(list(headers))
        for row in sample.to_dicts():
            ws_sample.append([row.get(h) for h in headers])

        # Summary sheet
        for key, value in summary.items():
            ws_summary.append([key.replace("_", " ").title(), value])

        wb.save(str(output_path))
        print(f"✅ Exported to {output_path}")
    except ImportError:
        sample.write_csv(output_path.with_suffix(".csv"))
        print(f"✅ Exported to {output_path.with_suffix('.csv')} (openpyxl not available)")
