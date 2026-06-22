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
    """Detect exceptions and assign to specific classes (max 1 primary class per row)."""
    exception_classes = []

    for row in df.iter_rows(named=True):
        exc_class = None

        # Check in priority order (first match wins)
        if (row["SANCTIONED_AMT"] is None or row["SANCTIONED_AMT"] <= 0):
            exc_class = "INVALID_SANCTIONED_AMT"
        elif row["OUTSTANDING_AMT"] and row["SANCTIONED_AMT"] and row["OUTSTANDING_AMT"] > row["SANCTIONED_AMT"]:
            exc_class = "OUTSTANDING_EXCEEDS_SANCTIONED"
        elif row["INTEREST_RATE"] is None or row["INTEREST_RATE"] <= 0 or row["INTEREST_RATE"] > 25:
            exc_class = "INVALID_INTEREST_RATE"
        elif row["TENURE_MONTHS"] is None or row["TENURE_MONTHS"] <= 0:
            exc_class = "INVALID_TENURE"
        elif row["KYC_STATUS"] in ["Missing", "Expired", "Pending"]:
            exc_class = "KYC_ISSUE"
        elif (row["LOAN_STATUS"] == "Closed") and (row["OUTSTANDING_AMT"] and row["OUTSTANDING_AMT"] > 0):
            exc_class = "CLOSED_WITH_OUTSTANDING"
        elif (row["LOAN_STATUS"] in ["Written-off", "NPA"]) and (row["DPD"] == 0):
            exc_class = "STATUS_DPD_MISMATCH"

        exception_classes.append(exc_class if exc_class else "CLEAN")

    return df.with_columns(pl.Series("EXCEPTION_CLASS", exception_classes).cast(pl.Utf8))


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
    """Audit sampling: exceptions (per-class) + strata + random."""
    n_pop = len(df)

    # Exception detection
    df = detect_and_flag_exceptions(df)
    df = compute_recency_weight(df)

    # Split
    df_exc = df.filter(pl.col("EXCEPTION_CLASS") != "CLEAN")
    df_clean = df.filter(pl.col("EXCEPTION_CLASS") == "CLEAN")

    n_exceptions = len(df_exc)
    n_clean = len(df_clean)

    # **Phase 1: Exception Sampling (max 10 per class, newest first)**
    sample_exc_list = []
    exception_classes = df_exc["EXCEPTION_CLASS"].unique().to_list()

    for exc_class in exception_classes:
        class_rows = df_exc.filter(pl.col("EXCEPTION_CLASS") == exc_class).sort("RECENCY_WEIGHT", descending=True)
        top_10 = class_rows.head(MAX_PER_EXCEPTION)
        sample_exc_list.append(top_10)

    sample_exc = pl.concat(sample_exc_list) if sample_exc_list else pl.DataFrame()

    # **Phase 2: Strata Coverage (1+ row per Product x Status x Branch)**
    strata_list = []
    strata_groups = df_clean.group_by(["PRODUCT", "LOAN_STATUS", "BRANCH"]).agg(pl.col("*").first())

    for row_dict in strata_groups.to_dicts():
        # Find any row matching this stratum
        stratum_row = df_clean.filter(
            (pl.col("PRODUCT") == row_dict["PRODUCT"]) &
            (pl.col("LOAN_STATUS") == row_dict["LOAN_STATUS"]) &
            (pl.col("BRANCH") == row_dict["BRANCH"])
        ).sort("RECENCY_WEIGHT", descending=True).head(1)
        if stratum_row.height > 0:
            strata_list.append(stratum_row)

    strata = pl.concat(strata_list) if strata_list else pl.DataFrame()
    n_strata = len(strata)

    # **Phase 3: Random Fill (from remaining clean, weighted by recency)**
    used_row_ids = set()
    if sample_exc.height > 0:
        used_row_ids.update(sample_exc["ROW_ID"].to_list())
    if strata.height > 0:
        used_row_ids.update(strata["ROW_ID"].to_list())

    remaining_clean = df_clean.filter(~df_clean["ROW_ID"].is_in(list(used_row_ids)))
    target_random = max(int(n_clean * TARGET_PCT), TARGET_MIN) - n_strata
    target_random = max(0, target_random)

    if target_random > 0 and len(remaining_clean) > 0:
        random.seed(SEED)
        weights = remaining_clean["RECENCY_WEIGHT"].to_list()
        total_w = sum(weights)
        probs = [w / total_w for w in weights] if total_w > 0 else [1.0 / len(weights)] * len(weights)
        indices = random.choices(range(len(remaining_clean)), weights=probs, k=min(target_random, len(remaining_clean)))
        sample_random = remaining_clean[indices]
    else:
        sample_random = pl.DataFrame()

    # Combine all samples
    samples = [s for s in [sample_exc, strata, sample_random] if s.height > 0]
    selected = pl.concat(samples, how="diagonal_relaxed") if samples else pl.DataFrame()

    summary = {
        "population_total": n_pop,
        "clean_records": n_clean,
        "exception_records": n_exceptions,
        "exception_classes_found": len(exception_classes),
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
