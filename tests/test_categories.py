"""Tests for rule categorization and filtered pipeline execution."""

from __future__ import annotations

import polars as pl

from fcmr_core.rules.registry import CATEGORIES, list_categories, resolve_rule_ids, run_pipeline


def test_categories_coverage():
    """Verify all registered rules appear in exactly one category."""
    from fcmr_core.rules.registry import _ensure_rules_loaded, list_rules

    _ensure_rules_loaded()
    all_rules = {m.rule_id for m in list_rules()}

    # Collect all rule_ids from categories
    categorized_rules = set()
    for cat in CATEGORIES:
        for rule_id in cat["rule_ids"]:
            assert rule_id in all_rules, f"Unknown rule in category: {rule_id}"
            assert rule_id not in categorized_rules, f"Rule {rule_id} in multiple categories"
            categorized_rules.add(rule_id)

    # All registered rules must be in exactly one category
    assert (
        categorized_rules == all_rules
    ), f"Missing rules: {all_rules - categorized_rules}, Extra: {categorized_rules - all_rules}"


def test_list_categories():
    """Verify list_categories returns enriched category data."""
    cats = list_categories()
    assert len(cats) == 5
    assert all("id" in c and "label" in c and "rules" in c and "count" in c for c in cats)
    assert {c["id"] for c in cats} == {
        "missing_data",
        "kyc_format",
        "address_pin",
        "duplicates",
        "identity_grouping",
    }
    cat_by_id = {c["id"]: c for c in cats}
    assert cat_by_id["missing_data"]["count"] == 8  # 7 missing rules + address_completeness
    assert cat_by_id["kyc_format"]["count"] == 11
    assert (
        cat_by_id["address_pin"]["count"] == 3
    )  # pincode_exists, state_pin_match, district_pin_match
    assert cat_by_id["duplicates"]["count"] == 7
    assert cat_by_id["identity_grouping"]["count"] == 2


def test_resolve_rule_ids_empty():
    """Resolve with no selection returns None (run all)."""
    result = resolve_rule_ids([], [])
    assert result is None


def test_resolve_rule_ids_by_category():
    """Resolve by category IDs."""
    result = resolve_rule_ids(["duplicates"], [])
    assert result is not None
    assert set(result) == {
        "pan_duplicate",
        "aadhaar_duplicate",
        "mobile_duplicate",
        "bank_account_duplicate",
        "name_dob_duplicate",
        "voter_id_duplicate",
        "address_duplicate",
    }


def test_resolve_rule_ids_by_rule():
    """Resolve by individual rule IDs."""
    result = resolve_rule_ids([], ["pan_format", "pincode_exists"])
    assert result == ["pan_format", "pincode_exists"]


def test_resolve_rule_ids_union():
    """Resolve merges categories and individual rules."""
    result = resolve_rule_ids(["address_pin"], ["pan_format"])
    expected = {
        "pincode_exists",
        "state_pin_match",
        "district_pin_match",
        "pan_format",
    }
    assert set(result) == expected


def test_run_pipeline_all_rules():
    """run_pipeline with rule_ids=None runs all rules."""
    from fcmr_core.rules.registry import _ensure_rules_loaded, list_rules

    _ensure_rules_loaded()
    all_rule_ids = {m.rule_id for m in list_rules()}

    # Create minimal test dataframe
    df = pl.DataFrame(
        {
            "customer_id": ["C001"],
            "pan": ["AAAA12023A"],
            "aadhaar": ["123456789012"],
            "full_name": ["Test"],
        }
    )

    annotated = run_pipeline(df, rule_ids=None)

    # Check all rules were executed (all _exc_* columns present)
    exc_cols = {c for c in annotated.columns if c.startswith("_exc_") and c.endswith("_status")}
    rule_ids_executed = {c[5:-7] for c in exc_cols}  # Extract between "_exc_" and "_status"
    assert rule_ids_executed == all_rule_ids


def test_run_pipeline_filtered():
    """run_pipeline with rule_ids filters to selected rules only."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001"],
            "pan": ["AAAA12023A"],
            "aadhaar": ["123456789012"],
            "full_name": ["Test"],
        }
    )

    # Run only duplicates category
    annotated = run_pipeline(df, rule_ids=["pan_duplicate", "aadhaar_duplicate"])

    # Check only selected rules were executed
    exc_cols = {c for c in annotated.columns if c.startswith("_exc_") and c.endswith("_status")}
    rule_ids_executed = {c[5:-7] for c in exc_cols}  # Extract between "_exc_" and "_status"
    assert rule_ids_executed == {"pan_duplicate", "aadhaar_duplicate"}


def test_run_pipeline_preserves_order():
    """run_pipeline preserves registry order even when filtered."""
    from fcmr_core.rules.registry import _ensure_rules_loaded, list_rules

    _ensure_rules_loaded()
    all_rules = list_rules()

    # Select a subset
    selected = ["pan_format", "pincode_exists", "pan_duplicate"]

    df = pl.DataFrame(
        {
            "customer_id": ["C001"],
            "pan": ["AAAA12023A"],
            "aadhaar": ["123456789012"],
            "full_name": ["Test"],
            "pincode": ["560001"],
        }
    )

    progress_calls = []

    def track_progress(completed: int, total: int, rule_id: str):
        progress_calls.append(rule_id)

    run_pipeline(df, on_progress=track_progress, rule_ids=selected)

    # Check progress calls match registry order
    expected_order = [r.rule_id for r in all_rules if r.rule_id in selected]
    assert progress_calls == expected_order


def test_run_pipeline_progress_callback():
    """on_progress callback receives correct completed/total counts."""
    df = pl.DataFrame(
        {
            "customer_id": ["C001"],
            "pan": ["AAAA12023A"],
            "aadhaar": ["123456789012"],
            "full_name": ["Test"],
        }
    )

    progress_calls = []

    def track_progress(completed: int, total: int, rule_id: str):
        progress_calls.append((completed, total, rule_id))

    # Run only 2 rules
    run_pipeline(df, on_progress=track_progress, rule_ids=["pan_format", "aadhaar_format"])

    # Check progress: completed should increment, total should be 2
    assert len(progress_calls) == 2
    assert progress_calls[0] == (1, 2, "pan_format")
    assert progress_calls[1] == (2, 2, "aadhaar_format")
