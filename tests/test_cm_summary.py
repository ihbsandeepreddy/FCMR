"""Tests for Customer Master summary analytics."""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics.cm_summary import generate_geographic_distribution


def test_geographic_distribution_basic():
    """Test geographic distribution with state and district."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003", "C004"],
            "state": ["KA", "KA", "MH", "MH"],
            "district": ["Bangalore", "Bangalore", "Mumbai", "Pune"],
        }
    )

    result = generate_geographic_distribution(df)

    assert len(result) == 3
    assert "state" in result.columns
    assert "district" in result.columns
    assert "Customer Count" in result.columns

    # KA/Bangalore should have 2 customers
    ka_bng = result.filter((pl.col("state") == "KA") & (pl.col("district") == "Bangalore"))
    assert len(ka_bng) > 0
    assert ka_bng[0, "Customer Count"] == 2


def test_geographic_distribution_no_state():
    """Test graceful handling when state column missing."""
    df = pl.DataFrame({"customer_id": ["C001"], "full_name": ["John"]})

    result = generate_geographic_distribution(df)

    assert "note" in result.columns
    assert result[0, "note"] == "state column not available"


def test_geographic_distribution_with_nulls():
    """Test filtering out null states."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003"],
            "state": ["KA", None, "MH"],
            "district": ["Bangalore", "Unknown", "Mumbai"],
        }
    )

    result = generate_geographic_distribution(df)

    # Only 2 non-null states should appear
    assert len(result) == 2
