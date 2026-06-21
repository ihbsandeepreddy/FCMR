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
