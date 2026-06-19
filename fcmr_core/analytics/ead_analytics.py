"""EAD Portfolio Analytics — Ind AS 109 / ECL report suite.

Operates on a merged Polars DataFrame of all EAD uploads for an engagement.
All 13 compute functions are pure Polars (vectorised, no Python loops).
Missing columns are skipped gracefully so the suite works even when a field
was not mapped or was not present in the source files.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Column maps
# ---------------------------------------------------------------------------

# canonical field name → display name used in pivot output columns
PIVOT_DIMENSION_CANONICAL: dict[str, str] = {
    "entity": "Entity",
    "source_system_id": "SourcesystemID",
    "scheme_id": "SchemeID",
    "scheme_name": "SchemeName",
    "branch_id": "BranchID",
    "branch_name": "BranchName",
    "state": "State",
    "sbu": "SBU",
    "sub_sbu": "SubSBU",
    "channel_code": "ChannelCode",
    "channel_desc": "ChannelCodeDesc",
    "loan_status": "LoanStatus",
    "stage": "Stage",
    "dpd_bucket": "DPDBucketing",
    "written_off": "WrittenOff",
}

# raw column names not in ead_files.yaml canonical schema — pass through as-is
PIVOT_DIMENSION_RAW: list[str] = [
    "System",
    "ECL",
    "WriteOffSecuSelldown",
    "ProductID",
    "ProductName",
    "FVTPL",
    "FuturePoS_GL_ID",
    "FuturePOS_GL_Des",
    "Principle_DRS_GL_ID",
    "Principle_DRS_GL_Des",
    "INT_DRS_GL_ID",
    "INT_DRS_GL_DESC",
    "Accrued_Interest_GL_ID",
    "Accrued_Interest_GL_DESC",
    "Redemption_Premium_Debtors_GL_ID",
    "Redemption_Premium_Debtors_GL_DESC",
    "Accrued_Redemption_Premium_GL_ID",
    "Accrued_Redemption_Premium_GL_DESC",
    "Prepaid_GL_ID",
    "Prepaid_GL_DESC",
]

# canonical field name → pivot output display name (SUM columns)
PIVOT_MEASURE_CANONICAL: dict[str, str] = {
    "future_pos": "Sum(FuturePOS)",
    "outstanding_principal": "Sum(DrsPOS)",
    "outstanding_interest": "Sum(DrsInt)",
    "accrued_interest": "Sum(AccruedInterest)",
    "overdue_charges": "Sum(OverDueCharges)",
    "gross_book_value": "Sum(Gross_Loans_and_Advances)",
    "ead": "Sum(EAD)",
    "mob": "Sum(MOB)",
    "collateral_value": "Sum(National_Asset_Value)",
    "covered_portion": "Sum(Covered_Portion)",
    "uncovered_portion": "Sum(Uncovered_Portion)",
    "existing_provision": "Sum(Provsion_as_per_Policy)",
    "additional_provision": "Sum(AdditionalProvision)",
    "total_provision": "Sum(Total_Provision)",
    "sanction_amount": "Sum(SANCTIONAMOUNT)",
    "disbursed_amount": "Sum(DISBURSEDAMOUNT)",
    "loan_id": "Count(AGREEMENTID_R)",  # COUNT, not SUM
    "principal_paid": "Sum(PrincipalPaid)",
    "interest_paid": "Sum(InterestPaid)",
    "emi_amount": "Sum(EMI Amount)",
}

# raw column names for measures not in the canonical schema
PIVOT_MEASURE_RAW: list[str] = [
    "Prepaid",
    "Debtors_Redemption_Premium",
    "AccruedRedemptionPremium",
    "TotalDebtors",
    "zero_90_days_interest",
    "zero_90_days_interest_Hist",
    "zero_90_int_Final",
    "Other Charges Paid",
    "PrinAdvance",
    "CBC Unpaid",
    "ODC Unpaid",
    "CBC",
    "ODC",
    "CBC Paid",
    "ODC Paid",
    "PROCESSINGFEES",
    "Unbanked",
]

# DPD bucket strings that imply > 90 days overdue
_HIGH_DPD_PATTERNS = ("91", "121", "151", "181", "211", "241", "271", "361", "npa", "sub", "doubtful", "loss")

# Loan status values indicating account closure / write-off
_CLOSED_STATUSES = {"closed", "written off", "writeoff", "wo", "write off", "settled", "foreclosed"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(df: pl.DataFrame, col: str) -> pl.Series:
    """Cast a column to Float64, returning nulls for non-numeric values."""
    return df[col].cast(pl.Float64, strict=False)


def _is_high_dpd(series: pl.Series) -> pl.Series:
    """Boolean mask: DPD bucket implies > 90 days overdue."""
    lower = series.cast(pl.Utf8, strict=False).str.to_lowercase().fill_null("")
    return lower.map_elements(
        lambda v: any(p in v for p in _HIGH_DPD_PATTERNS),
        return_dtype=pl.Boolean,
    )


def _available_dims(df: pl.DataFrame) -> list[str]:
    """Return canonical dimension column names present in df, in display-name order."""
    cols = []
    for canonical, display in PIVOT_DIMENSION_CANONICAL.items():
        if canonical in df.columns:
            cols.append(canonical)
    for raw in PIVOT_DIMENSION_RAW:
        if raw in df.columns:
            cols.append(raw)
    return cols


# ---------------------------------------------------------------------------
# 1. Master pivot report
# ---------------------------------------------------------------------------

def generate_pivot_report(df: pl.DataFrame) -> pl.DataFrame:
    """GROUP BY all available dimension columns, SUM/COUNT all measure columns."""
    dim_cols = _available_dims(df)
    if not dim_cols:
        # No dimension columns at all — return a single aggregate row
        dim_cols = []

    agg_exprs: list[pl.Expr] = []

    for canonical, display in PIVOT_MEASURE_CANONICAL.items():
        if canonical not in df.columns:
            continue
        col_f = _safe_float(df, canonical)
        tmp_col = f"__tmp_{canonical}"
        df = df.with_columns(col_f.alias(tmp_col))
        if canonical == "loan_id":
            agg_exprs.append(pl.col(tmp_col).count().alias(display))
        else:
            agg_exprs.append(pl.col(tmp_col).sum().alias(display))

    for raw in PIVOT_MEASURE_RAW:
        if raw not in df.columns:
            continue
        col_f = _safe_float(df, raw)
        tmp_col = f"__tmp_raw_{raw.replace(' ', '_')}"
        df = df.with_columns(col_f.alias(tmp_col))
        agg_exprs.append(pl.col(tmp_col).sum().alias(f"Sum({raw})"))

    if not agg_exprs:
        return pl.DataFrame()

    if dim_cols:
        result = df.group_by(dim_cols).agg(agg_exprs).sort(dim_cols)
    else:
        result = df.select(agg_exprs)

    # Drop temp columns from result (they shouldn't be there after agg, but be safe)
    result = result.select([c for c in result.columns if not c.startswith("__tmp_")])
    return result


# ---------------------------------------------------------------------------
# 2. Stage-wise ECL summary
# ---------------------------------------------------------------------------

def generate_stage_summary(df: pl.DataFrame) -> pl.DataFrame:
    if "stage" not in df.columns:
        return pl.DataFrame({"note": ["stage column not available"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "existing_provision" in df.columns:
        agg.append(pl.col("existing_provision").cast(pl.Float64, strict=False).sum().alias("Provision as per Policy"))
    if "additional_provision" in df.columns:
        agg.append(pl.col("additional_provision").cast(pl.Float64, strict=False).sum().alias("Additional Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))

    if not agg:
        return pl.DataFrame({"stage": df["stage"].unique()})

    result = df.group_by("stage").agg(agg).sort("stage")

    # Derived: coverage %
    if "Total EAD" in result.columns and "Total Provision" in result.columns:
        result = result.with_columns(
            (pl.col("Total Provision") / pl.col("Total EAD") * 100)
            .round(2)
            .alias("Coverage %")
        )

    return result


# ---------------------------------------------------------------------------
# 3. DPD bucket summary
# ---------------------------------------------------------------------------

def generate_dpd_summary(df: pl.DataFrame) -> pl.DataFrame:
    if "dpd_bucket" not in df.columns:
        return pl.DataFrame({"note": ["dpd_bucket column not available"]})

    agg: list[pl.Expr] = []
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "outstanding_principal" in df.columns:
        agg.append(pl.col("outstanding_principal").cast(pl.Float64, strict=False).sum().alias("Outstanding Principal"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))

    if not agg:
        return pl.DataFrame({"DPD Bucket": df["dpd_bucket"].unique()})

    return df.group_by("dpd_bucket").agg(agg).rename({"dpd_bucket": "DPD Bucket"}).sort("DPD Bucket")


# ---------------------------------------------------------------------------
# 4. Stage × DPD cross-tab
# ---------------------------------------------------------------------------

def generate_stage_dpd_crosstab(df: pl.DataFrame) -> pl.DataFrame:
    if "stage" not in df.columns or "dpd_bucket" not in df.columns:
        return pl.DataFrame({"note": ["stage or dpd_bucket column not available"]})

    agg: list[pl.Expr] = []
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))

    if not agg:
        agg = [pl.len().alias("Loan Count")]

    result = df.group_by(["stage", "dpd_bucket"]).agg(agg).sort(["stage", "dpd_bucket"])
    result = result.rename({"stage": "Stage", "dpd_bucket": "DPD Bucket"})

    # Flag: DPD > 90 but Stage = 1
    high_dpd = _is_high_dpd(result["DPD Bucket"])
    stage_1 = result["Stage"].cast(pl.Utf8, strict=False).str.strip_chars() == "1"
    result = result.with_columns(
        (high_dpd & stage_1).alias("DPD-Stage Mismatch Flag")
    )
    return result


# ---------------------------------------------------------------------------
# 5. Product-wise breakup
# ---------------------------------------------------------------------------

def generate_product_summary(df: pl.DataFrame) -> pl.DataFrame:
    group_cols = [c for c in ["scheme_id", "scheme_name"] if c in df.columns]
    if not group_cols:
        return pl.DataFrame({"note": ["scheme_id / scheme_name columns not available"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if not agg:
        agg = [pl.len().alias("Loan Count")]

    rename = {"scheme_id": "Product ID", "scheme_name": "Product Name"}
    return (
        df.group_by(group_cols).agg(agg)
        .rename({k: v for k, v in rename.items() if k in group_cols})
        .sort(group_cols[0])
    )


# ---------------------------------------------------------------------------
# 6. Geographic (state) concentration
# ---------------------------------------------------------------------------

def generate_geographic_summary(df: pl.DataFrame) -> pl.DataFrame:
    if "state" not in df.columns:
        return pl.DataFrame({"note": ["state column not available"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if not agg:
        agg = [pl.len().alias("Loan Count")]

    return df.group_by("state").agg(agg).rename({"state": "State"}).sort("State")


# ---------------------------------------------------------------------------
# 7. Secured vs unsecured
# ---------------------------------------------------------------------------

def generate_security_summary(df: pl.DataFrame) -> pl.DataFrame:
    if "stage" not in df.columns:
        return pl.DataFrame({"note": ["stage column not available"]})

    agg: list[pl.Expr] = []
    if "covered_portion" in df.columns:
        agg.append(pl.col("covered_portion").cast(pl.Float64, strict=False).sum().alias("Covered (Secured)"))
    if "uncovered_portion" in df.columns:
        agg.append(pl.col("uncovered_portion").cast(pl.Float64, strict=False).sum().alias("Uncovered (Unsecured)"))
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if not agg:
        return pl.DataFrame({"note": ["covered_portion / uncovered_portion columns not available"]})

    result = df.group_by("stage").agg(agg).rename({"stage": "Stage"}).sort("Stage")

    if "Covered (Secured)" in result.columns and "Total EAD" in result.columns:
        result = result.with_columns(
            (pl.col("Covered (Secured)") / pl.col("Total EAD") * 100)
            .round(2)
            .alias("Security Coverage %")
        )
    return result


# ---------------------------------------------------------------------------
# 8. Write-off summary
# ---------------------------------------------------------------------------

def generate_writeoff_summary(df: pl.DataFrame) -> pl.DataFrame:
    group_cols = [c for c in ["written_off", "stage"] if c in df.columns]
    if not group_cols:
        return pl.DataFrame({"note": ["written_off / stage columns not available"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if not agg:
        agg = [pl.len().alias("Loan Count")]

    return df.group_by(group_cols).agg(agg).sort(group_cols)


# ---------------------------------------------------------------------------
# 9. SBU / SubSBU breakdown
# ---------------------------------------------------------------------------

def generate_sbu_summary(df: pl.DataFrame) -> pl.DataFrame:
    group_cols = [c for c in ["sbu", "sub_sbu"] if c in df.columns]
    if not group_cols:
        return pl.DataFrame({"note": ["sbu / sub_sbu columns not available"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if not agg:
        agg = [pl.len().alias("Loan Count")]

    rename = {"sbu": "SBU", "sub_sbu": "Sub-SBU"}
    return (
        df.group_by(group_cols).agg(agg)
        .rename({k: v for k, v in rename.items() if k in group_cols})
        .sort(group_cols[0])
    )


# ---------------------------------------------------------------------------
# 10. Provision reasonableness check
# ---------------------------------------------------------------------------

def generate_provision_check(df: pl.DataFrame) -> pl.DataFrame:
    if "additional_provision" not in df.columns:
        return pl.DataFrame({"note": ["additional_provision column not available"]})

    ap = df["additional_provision"].cast(pl.Float64, strict=False).fill_null(0.0)
    filtered = df.filter(ap > 0)

    if filtered.is_empty():
        return pl.DataFrame({"note": ["No rows with additional_provision > 0"]})

    select_cols = [c for c in ["loan_id", "stage", "dpd_bucket", "ead"] if c in filtered.columns]
    result = filtered.select(select_cols + ["additional_provision"])

    if "existing_provision" in filtered.columns:
        result = result.with_columns(
            filtered["existing_provision"].cast(pl.Float64, strict=False).alias("existing_provision")
        )
        # ratio = additional / existing (avoid div by zero)
        result = result.with_columns(
            pl.when(pl.col("existing_provision") > 0)
            .then(pl.col("additional_provision").cast(pl.Float64, strict=False) / pl.col("existing_provision"))
            .otherwise(None)
            .round(4)
            .alias("Ratio (Addl/Policy)")
        )
        # Flag outliers: ratio > 2× median ratio
        ratios = result["Ratio (Addl/Policy)"].drop_nulls()
        if ratios.len() > 0:
            median_ratio = ratios.median()
            result = result.with_columns(
                (pl.col("Ratio (Addl/Policy)") > 2 * median_ratio).alias("Outlier Flag")
            )

    rename = {"loan_id": "Loan ID", "stage": "Stage", "dpd_bucket": "DPD Bucket", "ead": "EAD",
               "additional_provision": "Additional Provision", "existing_provision": "Policy Provision"}
    return result.rename({k: v for k, v in rename.items() if k in result.columns})


# ---------------------------------------------------------------------------
# 11. Negative values check
# ---------------------------------------------------------------------------

def generate_negative_check(df: pl.DataFrame) -> pl.DataFrame:
    numeric_canonical = [
        "ead", "outstanding_principal", "outstanding_interest", "accrued_interest",
        "overdue_charges", "future_pos", "gross_book_value", "collateral_value",
        "covered_portion", "uncovered_portion", "existing_provision",
        "additional_provision", "total_provision", "sanction_amount",
        "disbursed_amount", "principal_paid", "interest_paid", "emi_amount", "mob",
    ]
    numeric_raw = [
        "Prepaid", "TotalDebtors", "Debtors_Redemption_Premium", "AccruedRedemptionPremium",
        "zero_90_days_interest", "zero_90_int_Final", "PROCESSINGFEES", "Unbanked",
    ]
    all_numeric = [c for c in (numeric_canonical + numeric_raw) if c in df.columns]

    rows = []
    total = len(df)
    for col in all_numeric:
        series = df[col].cast(pl.Float64, strict=False)
        neg_count = (series < 0).sum()
        null_count = series.is_null().sum()
        rows.append({
            "Column": col,
            "Total Rows": total,
            "Negative Count": neg_count,
            "Null Count": null_count,
            "Has Issue": neg_count > 0,
        })

    return pl.DataFrame(rows) if rows else pl.DataFrame({"note": ["No numeric columns found"]})


# ---------------------------------------------------------------------------
# 12. Stage-DPD mismatch
# ---------------------------------------------------------------------------

def generate_stage_mismatch(df: pl.DataFrame) -> pl.DataFrame:
    if "stage" not in df.columns:
        return pl.DataFrame({"note": ["stage column not available"]})

    stage_str = df["stage"].cast(pl.Utf8, strict=False).str.strip_chars()
    conditions = []

    # DPD > 90 but classified as Stage 1
    if "dpd_bucket" in df.columns:
        high_dpd = _is_high_dpd(df["dpd_bucket"])
        conditions.append(high_dpd & (stage_str == "1"))

    # Loan closed/written-off but Stage 2 or 3
    if "loan_status" in df.columns:
        ls_lower = df["loan_status"].cast(pl.Utf8, strict=False).str.to_lowercase().fill_null("")
        is_closed = ls_lower.map_elements(
            lambda v: any(s in v for s in _CLOSED_STATUSES),
            return_dtype=pl.Boolean,
        )
        stage_23 = stage_str.is_in(["2", "3"])
        conditions.append(is_closed & stage_23)

    if not conditions:
        return pl.DataFrame({"note": ["Insufficient columns to detect mismatches"]})

    mask = conditions[0]
    for c in conditions[1:]:
        mask = mask | c

    result = df.filter(mask)
    if result.is_empty():
        return pl.DataFrame({"note": ["No stage-DPD mismatches found — data is consistent"]})

    keep_cols = [c for c in ["loan_id", "stage", "dpd_bucket", "loan_status", "ead"] if c in result.columns]
    return result.select(keep_cols).rename(
        {k: v for k, v in {"loan_id": "Loan ID", "stage": "Stage", "dpd_bucket": "DPD Bucket",
                            "loan_status": "Loan Status", "ead": "EAD"}.items() if k in keep_cols}
    )


# ---------------------------------------------------------------------------
# 13. FVTPL split
# ---------------------------------------------------------------------------

def generate_fvtpl_split(df: pl.DataFrame) -> pl.DataFrame:
    if "FVTPL" not in df.columns:
        return pl.DataFrame({"note": ["FVTPL column not available (not mapped or not in source data)"]})

    agg: list[pl.Expr] = []
    if "ead" in df.columns:
        agg.append(pl.col("ead").cast(pl.Float64, strict=False).sum().alias("Total EAD"))
    if "total_provision" in df.columns:
        agg.append(pl.col("total_provision").cast(pl.Float64, strict=False).sum().alias("Total Provision"))
    if "loan_id" in df.columns:
        agg.append(pl.col("loan_id").count().alias("Loan Count"))
    if not agg:
        agg = [pl.len().alias("Loan Count")]

    return df.group_by("FVTPL").agg(agg).sort("FVTPL")


# ---------------------------------------------------------------------------
# Excel workpaper builder
# ---------------------------------------------------------------------------

_REPORT_SHEET_NAMES: list[tuple[str, str]] = [
    ("pivot", "Pivot Report"),
    ("stage_summary", "Stage Summary"),
    ("dpd_summary", "DPD Summary"),
    ("stage_dpd", "Stage x DPD"),
    ("product", "Product Breakup"),
    ("geographic", "Geography"),
    ("security", "Secured vs Unsecured"),
    ("writeoff", "Write-Off Summary"),
    ("sbu", "SBU Breakdown"),
    ("provision_check", "Provision Check"),
    ("negative_check", "Negative Values"),
    ("stage_mismatch", "Stage Mismatch"),
    ("fvtpl", "FVTPL Split"),
]


def _write_sheet(ws, df: pl.DataFrame, header_fill, header_font, data_font) -> None:
    """Write a Polars DataFrame to an openpyxl worksheet."""
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    cols = df.columns
    for ci, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=ci, value=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    str_df = df.with_columns([pl.col(c).cast(pl.Utf8, strict=False) for c in cols])
    for ri, row in enumerate(str_df.rows(), 2):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=val if val not in (None, "None", "null") else None)
            cell.font = data_font

    for ci, col in enumerate(cols, 1):
        max_len = min(max(len(col), 10), 40)
        ws.column_dimensions[get_column_letter(ci)].width = max_len + 2

    if len(df) > 0:
        ws.freeze_panes = "A2"


def build_ead_workpaper(reports: dict[str, pl.DataFrame], output_path: Path) -> None:
    """Write all 13 EAD reports into one multi-sheet Excel workpaper."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="5C3D1E", end_color="5C3D1E", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    data_font = Font(size=10)

    first = True
    for key, sheet_name in _REPORT_SHEET_NAMES:
        df = reports.get(key)
        if df is None or df.is_empty():
            continue
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(sheet_name)
        _write_sheet(ws, df, header_fill, header_font, data_font)

    if first:
        # All empty — write a placeholder
        ws = wb.active
        ws.title = "Summary"
        ws["A1"] = "No data available"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

_REPORT_FUNCTIONS = [
    ("pivot", generate_pivot_report, "Master Pivot Report"),
    ("stage_summary", generate_stage_summary, "Stage Summary"),
    ("dpd_summary", generate_dpd_summary, "DPD Bucket Summary"),
    ("stage_dpd", generate_stage_dpd_crosstab, "Stage × DPD Cross-tab"),
    ("product", generate_product_summary, "Product Breakup"),
    ("geographic", generate_geographic_summary, "Geographic Concentration"),
    ("security", generate_security_summary, "Secured vs Unsecured"),
    ("writeoff", generate_writeoff_summary, "Write-Off Summary"),
    ("sbu", generate_sbu_summary, "SBU / SubSBU Breakdown"),
    ("provision_check", generate_provision_check, "Provision Reasonableness"),
    ("negative_check", generate_negative_check, "Negative Values Check"),
    ("stage_mismatch", generate_stage_mismatch, "Stage-DPD Mismatch"),
    ("fvtpl", generate_fvtpl_split, "FVTPL Split"),
]


def run_ead_analytics(
    df: pl.DataFrame,
    output_dir: Path,
    on_progress=None,
) -> dict[str, Path]:
    """Run all 13 EAD reports, write CSVs + Excel workpaper, return {name: path}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(_REPORT_FUNCTIONS)
    reports: dict[str, pl.DataFrame] = {}
    paths: dict[str, Path] = {}

    for i, (key, fn, label) in enumerate(_REPORT_FUNCTIONS):
        if on_progress:
            on_progress(i, total, label)
        try:
            result = fn(df)
            reports[key] = result
            if not result.is_empty():
                csv_path = output_dir / f"{key}.csv"
                result.write_csv(str(csv_path))
                paths[key] = csv_path
        except Exception as exc:  # noqa: BLE001
            # One report failure must not abort the whole suite
            reports[key] = pl.DataFrame({"error": [str(exc)]})

    if on_progress:
        on_progress(total - 1, total, "Building Excel workpaper")

    workpaper_path = output_dir / "ead_workpaper.xlsx"
    try:
        build_ead_workpaper(reports, workpaper_path)
        paths["workpaper"] = workpaper_path
    except Exception:
        pass

    if on_progress:
        on_progress(total, total, "Complete")

    return paths


# ---------------------------------------------------------------------------
# Summary stats (for the result page header cards)
# ---------------------------------------------------------------------------

def compute_summary_stats(df: pl.DataFrame) -> dict:
    """Return high-level numbers for the four stat cards on the results page."""
    stats: dict = {}

    if "loan_id" in df.columns:
        stats["total_loans"] = df["loan_id"].count()
    elif len(df) > 0:
        stats["total_loans"] = len(df)
    else:
        stats["total_loans"] = 0

    if "ead" in df.columns:
        stats["total_ead"] = df["ead"].cast(pl.Float64, strict=False).sum()
    else:
        stats["total_ead"] = None

    if "total_provision" in df.columns:
        stats["total_provision"] = df["total_provision"].cast(pl.Float64, strict=False).sum()
    else:
        stats["total_provision"] = None

    if stats.get("total_ead") and stats.get("total_provision") and stats["total_ead"] > 0:
        stats["coverage_pct"] = round(stats["total_provision"] / stats["total_ead"] * 100, 2)
    else:
        stats["coverage_pct"] = None

    return stats
