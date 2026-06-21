"""Tests for Customer Master summary analytics."""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics.cm_summary import (
    generate_cluster_distribution,
    generate_coapplicant_overlap,
    generate_data_quality_summary,
    generate_demographic_distribution,
    generate_duplication_summary,
    generate_geographic_distribution,
    generate_kyc_completeness,
    generate_lan_concentration,
)


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


def test_kyc_completeness():
    """Test KYC field completeness calculation."""
    df = pl.DataFrame(
        {
            "pan": ["AAAA12023A", None, "BBBB34045B"],
            "mobile": ["9876543210", "9876543210", None],
            "email": [None, None, "test@example.com"],
        }
    )

    result = generate_kyc_completeness(df)

    assert "Field" in result.columns
    assert "Percent Present" in result.columns
    # PAN: 2/3 = 66.67%
    pan_row = result.filter(pl.col("Field") == "Pan")
    assert len(pan_row) > 0
    assert pan_row[0, "Percent Present"] > 66 and pan_row[0, "Percent Present"] < 67


def test_demographic_distribution():
    """Test age bucket distribution."""
    from datetime import datetime, timedelta

    today = datetime.now()
    dob_25yo = (today - timedelta(days=365 * 25)).strftime("%d-%m-%Y")
    dob_45yo = (today - timedelta(days=365 * 45)).strftime("%d-%m-%Y")

    df = pl.DataFrame(
        {
            "dob": [dob_25yo, dob_45yo, None],
            "gender": ["M", "F", "M"],
            "customer_id": ["C001", "C002", "C003"],
        }
    )

    result = generate_demographic_distribution(df)

    assert "age_bucket" in result.columns
    assert len(result) >= 1  # At least 1 age bucket


def test_duplication_summary():
    """Test duplication count aggregation."""
    df = pl.DataFrame(
        {
            "rule_id": ["pan_duplicate", "pan_duplicate", "aadhaar_duplicate"],
            "status": ["ERROR", "ERROR", "ERROR"],
        }
    )

    result = generate_duplication_summary(df)

    assert "Duplicate Type" in result.columns
    assert "Count" in result.columns
    pan_dup = result.filter(pl.col("Duplicate Type").str.contains("Pan"))
    assert len(pan_dup) > 0


def test_coapplicant_overlap():
    """Test co-applicant mobile overlap detection."""
    df = pl.DataFrame(
        {
            "mobile": ["9876543210", "9123456789"],
            "coapplicant_mobile": ["9876543210", "9999999999"],
        }
    )

    result = generate_coapplicant_overlap(df)

    assert "Overlap Status" in result.columns
    assert len(result) == 2  # Match + no-match rows


def test_cluster_distribution():
    """Test UCID cluster size distribution."""
    df = pl.DataFrame(
        {
            "ucid_size": [1, 2, 5, 10, 15],
            "customer_id": ["C001", "C002", "C003", "C004", "C005"],
        }
    )

    result = generate_cluster_distribution(df)

    assert "cluster_size_band" in result.columns
    assert len(result) >= 1


def test_data_quality_summary():
    """Test missing rate calculation."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", None],
            "pan": ["AAAA12023A", None, None],
            "mobile": ["9876543210", "9123456789", "9098765432"],
        }
    )

    result = generate_data_quality_summary(df)

    assert "Column" in result.columns
    assert "Percent Missing" in result.columns
    # customer_id: 1/3 missing = 33.33%
    cust_row = result.filter(pl.col("Column").str.contains("Customer"))
    assert len(cust_row) > 0


def test_lan_concentration():
    """Test LAN concentration (top customers by distinct loans)."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C001", "C001", "C002", "C002"],
            "lan": ["L001", "L002", "L003", "L004", "L005"],
            "ucid": ["U001", "U001", "U001", "U002", "U002"],
        }
    )

    result = generate_lan_concentration(df, top_n=2)

    assert "Rank" in result.columns
    assert "customer_id" in result.columns
    assert "Distinct LANs" in result.columns
    # C001 should be rank 1 with 3 distinct LANs
    assert result[0, "Distinct LANs"] == 3
