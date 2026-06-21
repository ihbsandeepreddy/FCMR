"""Tests for CM best-practice analytics."""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics.cm_analytics import generate_aadhaar_coverage


def test_aadhaar_coverage_basic():
    """Test Aadhaar coverage calculation."""
    df = pl.DataFrame(
        {
            "aadhaar": ["123456789012", "234567890123", None, "456789012345"],
        }
    )

    result = generate_aadhaar_coverage(df)

    assert "Coverage Status" in result.columns
    assert "Count" in result.columns
    assert "Percent" in result.columns
    # 3/4 = 75%
    present = result.filter(pl.col("Coverage Status") == "Present")[0, "Percent"]
    assert present == 75.0


def test_aadhaar_coverage_all_present():
    """Test when all customers have Aadhaar."""
    df = pl.DataFrame(
        {
            "aadhaar": ["111111111111", "222222222222", "333333333333"],
        }
    )

    result = generate_aadhaar_coverage(df)

    present = result.filter(pl.col("Coverage Status") == "Present")[0, "Percent"]
    assert present == 100.0


def test_aadhaar_coverage_all_missing():
    """Test when no customers have Aadhaar."""
    df = pl.DataFrame(
        {
            "aadhaar": [None, None, None],
        }
    )

    result = generate_aadhaar_coverage(df)

    present = result.filter(pl.col("Coverage Status") == "Present")[0, "Percent"]
    assert present == 0.0


def test_aadhaar_coverage_no_column():
    """Test when aadhaar column is missing."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002"],
        }
    )

    result = generate_aadhaar_coverage(df)

    assert "note" in result.columns
    assert result[0, "note"] == "aadhaar column required"
