"""Golden test for UCID rule output (locks current behavior)."""

from __future__ import annotations

import polars as pl

from fcmr_core.rules.registry import run_pipeline


def test_ucid_golden_output():
    """Golden test: verify UCID columns and status are stable across versions.

    This test locks the current UCID output format and behavior.
    Changes to UCID logic must maintain backward-compatible output.
    """
    # Minimal fixture: 3 rows, 2 customers (same PAN = should be grouped)
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002", "C003"],
            "pan": ["AAAA0000A", "BBBB1111B", "AAAA0000A"],  # C001 and C003 share PAN
            "aadhaar": ["", "", ""],
            "mobile": ["", "", ""],
            "email": ["", "", ""],
            "full_name": ["Customer 1", "Customer 2", "Customer 1"],
            "dob": ["", "", ""],
            "state": ["KA", "MH", "KA"],
            "pincode": ["560001", "400001", "560001"],
            "address": ["Bangalore", "Mumbai", "Bangalore"],
            "lan": ["L001", "L002", "L003"],  # All different loans
        }
    )

    # Run UCID rule only
    result = run_pipeline(df, rule_ids=["ucid"])

    # Verify expected columns exist
    assert "_exc_ucid_status" in result.columns, "UCID status column missing"
    assert "_exc_ucid_code" in result.columns, "UCID code column missing"
    assert "_exc_ucid_desc" in result.columns, "UCID description column missing"
    assert "ucid" in result.columns, "UCID group column missing"
    assert "ucid_size" in result.columns, "UCID group size column missing"

    # Verify status is OK (no UCID inconsistency expected; same PAN, same state/pin)
    statuses = result.get_column("_exc_ucid_status").to_list()
    assert all(s == "OK" for s in statuses), f"Expected all OK, got {statuses}"

    # Verify UCID grouping: rows 0 and 2 should have same UCID
    ucids = result.get_column("ucid").to_list()
    assert (
        ucids[0] == ucids[2]
    ), f"Rows 0 and 2 should be in same UCID, got {ucids[0]} vs {ucids[2]}"
    assert ucids[0] != ucids[1], f"Row 1 should be in different UCID, got {ucids[1]}"

    # Verify group size
    sizes = result.get_column("ucid_size").to_list()
    assert sizes[0] == 2, f"UCID group 0 should have size 2, got {sizes[0]}"
    assert sizes[1] == 1, f"UCID group 1 should have size 1, got {sizes[1]}"
    assert sizes[2] == 2, f"UCID group 2 should have size 2, got {sizes[2]}"


def test_ucid_inconsistency_detection():
    """Test that UCID detects KYC inconsistency within a group."""
    # Same PAN but different states = should flag inconsistency
    df = pl.DataFrame(
        {
            "customer_id": ["C001", "C002"],
            "pan": ["AAAA0000A", "AAAA0000A"],  # Same PAN
            "aadhaar": ["", ""],
            "mobile": ["", ""],
            "email": ["", ""],
            "full_name": ["Customer 1", "Customer 1"],
            "dob": ["", ""],
            "state": ["KA", "MH"],  # Different states!
            "pincode": ["560001", "400001"],
            "address": ["Bangalore", "Mumbai"],
            "lan": ["L001", "L002"],
        }
    )

    result = run_pipeline(df, rule_ids=["ucid"])

    # Rows should be grouped (same PAN)
    ucids = result.get_column("ucid").to_list()
    assert ucids[0] == ucids[1], "Same PAN should group together"

    # But status should flag inconsistency
    statuses = result.get_column("_exc_ucid_status").to_list()
    codes = result.get_column("_exc_ucid_code").to_list()
    assert any(s == "WARN" for s in statuses), f"Expected WARN for inconsistency, got {statuses}"
    assert any("INCONSISTENT" in str(c) for c in codes), f"Expected INCONSISTENT code, got {codes}"
