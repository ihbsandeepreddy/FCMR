"""Determinism + priority tests for beneficiary tagging (C3)."""

from __future__ import annotations

import polars as pl

from fcmr_core.rules.beneficiary import rule_beneficiary_tagging


def _keys(df: pl.DataFrame):
    out = rule_beneficiary_tagging(df)
    return out["fcmr_customer_key"].to_list(), out["fcmr_group_id"].to_list()


def test_blank_identity_rows_are_deterministic():
    """All-blank-identity rows must yield identical keys across runs (no id())."""
    df = pl.DataFrame(
        {
            "customer_id": ["", ""],
            "pan": ["", ""],
            "aadhaar": ["", ""],
            "mobile": ["", ""],
            "full_name": ["", ""],
            "dob": ["", ""],
            "_row_num": ["1", "2"],
        }
    )
    ck1, gk1 = _keys(df)
    ck2, gk2 = _keys(df)
    assert ck1 == ck2, "customer keys must be reproducible across runs"
    assert gk1 == gk2, "group ids must be reproducible across runs"
    # Distinct unidentifiable rows must not collapse into one another.
    assert ck1[0] != ck1[1]


def test_identifier_priority_pan_first():
    df = pl.DataFrame(
        {
            "customer_id": ["C1"],
            "pan": ["ABCPK1234A"],
            "aadhaar": [""],
            "mobile": ["9876543210"],
            "full_name": ["X"],
            "dob": ["1990-01-01"],
        }
    )
    ck, _ = _keys(df)
    assert ck[0].startswith("PAN:")
