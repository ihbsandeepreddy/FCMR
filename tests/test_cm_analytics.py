"""Tests for CM best-practice analytics."""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics.cm_analytics import (
    generate_aadhaar_coverage,
    generate_coapplicant_concentration,
    generate_fraud_risk_flags,
)


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


def test_fraud_risk_flags_missing_pan():
    """Test detection of missing PAN."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003"],
            "pan": ["ABC1234", None, "DEF5678"],
        }
    )

    result = generate_fraud_risk_flags(df)

    missing_pan = result.filter(pl.col("Risk Category") == "Missing PAN")
    assert len(missing_pan) > 0
    assert missing_pan[0, "Customer Count"] == 1


def test_fraud_risk_flags_missing_aadhaar():
    """Test detection of missing Aadhaar."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003"],
            "aadhaar": ["123456789012", None, "234567890123"],
        }
    )

    result = generate_fraud_risk_flags(df)

    missing_aadhaar = result.filter(pl.col("Risk Category") == "Missing Aadhaar")
    assert len(missing_aadhaar) > 0
    assert missing_aadhaar[0, "Customer Count"] == 1


def test_fraud_risk_flags_multiple_mobiles():
    """Test detection of multiple mobiles per customer."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C001", "C002"],
            "mobile": ["9876543210", "9876543211", "8765432109"],
            "ucid": ["U001", "U001", "U002"],
        }
    )

    result = generate_fraud_risk_flags(df)

    multi_mobile = result.filter(pl.col("Risk Category") == "Multiple Mobiles per Customer")
    assert len(multi_mobile) > 0
    assert multi_mobile[0, "Customer Count"] == 1


def test_fraud_risk_flags_no_column():
    """Test when customer_id column is missing."""
    df = pl.DataFrame(
        {
            "name": ["Alice", "Bob"],
        }
    )

    result = generate_fraud_risk_flags(df)

    assert "note" in result.columns
    assert result[0, "note"] == "customer_id column required"


def test_coapplicant_concentration_basic():
    """Test detection of co-applicants linked to multiple primaries."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003"],
            "coapplicant_mobile": ["9876543210", "9876543210", "9999999999"],
            "lan": ["L001", "L002", "L003"],
        }
    )

    result = generate_coapplicant_concentration(df)

    assert "Primary_Applicants" in result.columns
    assert "Loan_Count" in result.columns
    # Co-applicant 9876543210 linked to 2 primaries
    assert len(result) > 0
    assert result[0, "Primary_Applicants"] == 2


def test_coapplicant_concentration_no_shared():
    """Test when no co-applicant is shared across primaries."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002"],
            "coapplicant_mobile": ["9876543210", "8765432109"],
            "lan": ["L001", "L002"],
        }
    )

    result = generate_coapplicant_concentration(df)

    assert "note" in result.columns
    assert result[0, "note"] == "No concentrated co-applicant relationships"


def test_coapplicant_concentration_no_column():
    """Test when coapplicant_mobile column is missing."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002"],
            "lan": ["L001", "L002"],
        }
    )

    result = generate_coapplicant_concentration(df)

    assert "note" in result.columns
    assert result[0, "note"] == "coapplicant_mobile column required"
