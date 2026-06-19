"""Analytics aggregation: status counts, exception code frequencies.

Reads wide CSV outputs and aggregates exception data for dashboard display.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


def aggregate_status_counts(wide_csv_path: Path) -> dict[str, int]:
    """Count rows per overall_status: OK, WARN, ERROR.

    Args:
        wide_csv_path: Path to the wide exception CSV (one row per input record).

    Returns:
        {status: count} e.g. {"OK": 1200, "WARN": 340, "ERROR": 18}
    """
    if not wide_csv_path.exists():
        return {"OK": 0, "WARN": 0, "ERROR": 0}

    try:
        df = pl.read_csv(wide_csv_path, columns=["overall_status"], infer_schema_length=0)
        counts = df["overall_status"].value_counts(sort=True).to_dicts()
        # Polars ≥0.19 names the count column "count"; older versions used "counts"
        count_key = "count" if counts and "count" in counts[0] else "counts"
        result = {row["overall_status"]: row[count_key] for row in counts}
        # Ensure all statuses are present
        return {
            "OK": result.get("OK", 0),
            "WARN": result.get("WARN", 0),
            "ERROR": result.get("ERROR", 0),
        }
    except Exception:
        return {"OK": 0, "WARN": 0, "ERROR": 0}


def aggregate_exception_codes(wide_csv_path: Path, top_n: int | None = 10) -> dict[str, int]:
    """Count top N exception codes from exception_codes column (pipe-delimited).

    Args:
        wide_csv_path: Path to the wide exception CSV.
        top_n: Number of top codes to return. None = all codes.

    Returns:
        {exception_code: count} sorted by frequency descending.
    """
    if not wide_csv_path.exists():
        return {}

    try:
        df = pl.read_csv(wide_csv_path, columns=["exception_codes"], infer_schema_length=0)
        # Parse pipe-delimited codes
        all_codes = []
        for codes_str in df["exception_codes"]:
            if codes_str and str(codes_str).strip():
                codes = [c.strip() for c in str(codes_str).split("|") if c.strip()]
                all_codes.extend(codes)

        # Count and sort
        code_counts = {}
        for code in all_codes:
            code_counts[code] = code_counts.get(code, 0) + 1

        # Return top N (or all if top_n is None)
        sorted_codes = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)
        limit = top_n if top_n is not None else len(sorted_codes)
        return {code: count for code, count in sorted_codes[:limit]}
    except Exception:
        return {}


_MISSING_CODES = {
    "PAN_MISSING",
    "AADHAAR_MISSING",
    "VOTER_ID_MISSING",
    "MOBILE_MISSING",
    "EMAIL_MISSING",
    "DOB_MISSING",
    "PIN_MISSING",
    "ADDRESS_INCOMPLETE",
}

_MISSING_LABELS = {
    "PAN_MISSING": "PAN",
    "AADHAAR_MISSING": "Aadhaar",
    "VOTER_ID_MISSING": "Voter ID",
    "MOBILE_MISSING": "Mobile",
    "EMAIL_MISSING": "Email",
    "DOB_MISSING": "Date of Birth",
    "PIN_MISSING": "Pincode",
    "ADDRESS_INCOMPLETE": "Address (incomplete)",
}


def aggregate_missing_data(long_csv_path: Path, total_rows: int) -> list[dict]:
    """Count missing-field occurrences per code from the long exception CSV.

    Args:
        long_csv_path: Path to the long exception CSV (one row per exception).
        total_rows: Total record count (denominator for % calculation).

    Returns:
        List of {field, code, count, pct} sorted by count descending,
        only for codes in _MISSING_CODES.
    """
    if not long_csv_path.exists() or total_rows == 0:
        return []

    try:
        df = pl.read_csv(
            long_csv_path, columns=["exception_code"], infer_schema_length=0
        )
        counts: dict[str, int] = {}
        for code in df["exception_code"]:
            if code and code in _MISSING_CODES:
                counts[code] = counts.get(code, 0) + 1

        result = []
        for code, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            result.append(
                {
                    "field": _MISSING_LABELS.get(code, code),
                    "code": code,
                    "count": cnt,
                    "pct": round(cnt / total_rows * 100, 1),
                }
            )
        return result
    except Exception:
        return []


def get_summary(wide_csv_path: Path) -> dict:
    """Get a complete summary: status counts, top exceptions, total rows.

    Args:
        wide_csv_path: Path to the wide exception CSV.

    Returns:
        {
            "total_rows": int,
            "status_counts": {status: count},
            "exception_codes": {code: count},
        }
    """
    status_counts = aggregate_status_counts(wide_csv_path)
    exception_codes = aggregate_exception_codes(wide_csv_path, top_n=10)
    total_rows = sum(status_counts.values())

    return {
        "total_rows": total_rows,
        "status_counts": status_counts,
        "exception_codes": exception_codes,
    }
