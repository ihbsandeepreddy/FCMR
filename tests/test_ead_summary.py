"""Tests for EAD summary analytics."""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics.ead_summary import (
    generate_collateral_coverage,
    generate_data_quality_summary_ead,
    generate_dpd_risk_distribution,
    generate_portfolio_concentration,
    generate_provision_coverage,
    generate_sanction_disbursement_variance,
    generate_stage_distribution,
    generate_writeoff_recovery,
)


def test_portfolio_concentration():
    """Test portfolio concentration (top loans by EAD)."""
    df = pl.DataFrame(
        {
            "loan_id": ["L001", "L002", "L003", "L001", "L002"],
            "ead": [100000, 50000, 75000, 25000, 150000],
        }
    )

    result = generate_portfolio_concentration(df, top_n=2)

    assert "Rank" in result.columns
    assert "loan_id" in result.columns
    assert "Total EAD" in result.columns
    # L002 has highest EAD (150000 + 50000 = 200000)
    assert result[0, "loan_id"] == "L002"


def test_stage_distribution():
    """Test stage distribution by count and EAD."""
    df = pl.DataFrame(
        {
            "stage": ["Stage 1", "Stage 1", "Stage 2", "Stage 3"],
            "loan_id": ["L001", "L002", "L003", "L004"],
            "ead": [100000, 50000, 75000, 25000],
        }
    )

    result = generate_stage_distribution(df)

    assert "stage" in result.columns
    assert "Loan Count" in result.columns
    assert "Total EAD" in result.columns
    # Stage 1 should have 2 loans
    stage1 = result.filter(pl.col("stage") == "Stage 1")
    assert len(stage1) > 0
    assert stage1[0, "Loan Count"] == 2


def test_dpd_risk_distribution():
    """Test DPD risk distribution."""
    df = pl.DataFrame(
        {
            "dpd_bucket": ["0-30", "31-60", "0-30", "NPA"],
            "loan_id": ["L001", "L002", "L003", "L004"],
            "ead": [100000, 50000, 75000, 25000],
        }
    )

    result = generate_dpd_risk_distribution(df)

    assert "dpd_bucket" in result.columns
    assert len(result) >= 1


def test_collateral_coverage():
    """Test collateral coverage analysis."""
    df = pl.DataFrame(
        {
            "ead": [100000, 50000, 75000],
            "collateral_value": [80000, 25000, None],
        }
    )

    result = generate_collateral_coverage(df)

    assert "Coverage Type" in result.columns
    assert "Amount" in result.columns
    # Covered: 80000 + 25000 = 105000; Total: 225000
    covered = result.filter(pl.col("Coverage Type") == "Covered")[0, "Amount"]
    assert covered == 105000


def test_provision_coverage():
    """Test provision coverage analysis."""
    df = pl.DataFrame(
        {
            "ead": [100000, 50000, 75000],
            "total_provision": [10000, 5000, 7500],
        }
    )

    result = generate_provision_coverage(df)

    assert "Coverage Type" in result.columns
    assert "Amount" in result.columns
    # Total EAD: 225000, Total provision: 22500
    total_ead = result.filter(pl.col("Coverage Type") == "Total Exposure")[0, "Amount"]
    assert total_ead == 225000


def test_writeoff_recovery():
    """Test write-off and recovery summary."""
    df = pl.DataFrame(
        {
            "written_off": ["No", "No", "Yes"],
            "loan_id": ["L001", "L002", "L003"],
            "ead": [100000, 50000, 75000],
        }
    )

    result = generate_writeoff_recovery(df)

    assert "written_off" in result.columns
    assert len(result) >= 1


def test_sanction_disbursement_variance():
    """Test sanction vs disbursement analysis."""
    df = pl.DataFrame(
        {
            "sanction_amount": [100000, 50000, 75000],
            "disbursed_amount": [80000, 50000, 50000],
        }
    )

    result = generate_sanction_disbursement_variance(df)

    assert "Amount Type" in result.columns
    # Total sanctioned: 225000, Total disbursed: 180000
    sanctioned = result.filter(pl.col("Amount Type") == "Sanctioned")[0, "Amount"]
    assert sanctioned == 225000


def test_string_typed_numeric_columns_do_not_break_summaries():
    """H2: string-typed numeric columns must summarise (cast), not error into 'note'."""
    df = pl.DataFrame(
        {
            "loan_id": ["L001", "L002", "L003"],
            "stage": ["Stage 1", "Stage 2", "Stage 3"],
            "ead": ["100000", "50000", "75000"],  # VARCHAR, not numeric
            "total_provision": ["1000", "500", "750"],
        }
    )
    stage = generate_stage_distribution(df)
    assert "note" not in stage.columns
    assert stage["Total EAD"].sum() == 225000.0

    prov = generate_provision_coverage(df)
    assert "note" not in prov.columns
    total = prov.filter(pl.col("Coverage Type") == "Total Exposure")[0, "Amount"]
    assert total == 225000.0


def test_data_quality_summary_ead():
    """Test EAD data quality summary."""
    df = pl.DataFrame(
        {
            "loan_id": ["L001", "L002", None],
            "stage": ["Stage 1", None, "Stage 2"],
            "ead": [100000, 50000, 75000],
        }
    )

    result = generate_data_quality_summary_ead(df)

    assert "Column" in result.columns
    assert "Percent Missing" in result.columns
    # loan_id: 1/3 missing = 33.33%
    loan_col = result.filter(pl.col("Column").str.contains("Loan"))
    assert len(loan_col) > 0
