"""Robustness: the rule pipeline must never crash on degenerate inputs.

Codifies the contract that a single bad/empty/odd frame cannot abort a run, and that
every rule appends its three _exc_* columns of the correct length.
"""

from __future__ import annotations

import polars as pl
import pytest

from fcmr_core.rules.registry import _ensure_rules_loaded, list_rules, run_pipeline

_ensure_rules_loaded()
_RULE_IDS = [m.rule_id for m in list_rules()]


def _assert_annotated(df_in: pl.DataFrame, annotated: pl.DataFrame):
    for rid in _RULE_IDS:
        for suffix in ("status", "code", "desc"):
            col = f"_exc_{rid}_{suffix}"
            assert col in annotated.columns, f"missing {col}"
    assert annotated.height == df_in.height


def test_zero_row_frame():
    df = pl.DataFrame(
        {"customer_id": [], "full_name": [], "lan": []},
        schema={"customer_id": pl.Utf8, "full_name": pl.Utf8, "lan": pl.Utf8},
    )
    _assert_annotated(df, run_pipeline(df))


def test_frame_missing_all_canonical_columns():
    df = pl.DataFrame({"some_unrelated_col": ["a", "b", "c"]})
    _assert_annotated(df, run_pipeline(df))


def test_frame_with_all_null_canonical_columns():
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "pan": [None, None],
            "aadhaar": [None, None],
            "mobile": [None, None],
            "full_name": [None, None],
            "dob": [None, None],
            "pincode": [None, None],
            "address_line1": [None, None],
        }
    )
    _assert_annotated(df, run_pipeline(df))


@pytest.mark.parametrize("rule_id", _RULE_IDS)
def test_each_rule_on_single_blank_row(rule_id):
    """Every rule, run individually, tolerates a single all-blank row."""
    df = pl.DataFrame({"customer_id": [""], "_row_num": ["1"]})
    annotated = run_pipeline(df, rule_ids=[rule_id])
    assert f"_exc_{rule_id}_status" in annotated.columns
