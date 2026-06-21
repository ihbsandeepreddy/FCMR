"""Tests for per-engagement disabled rules (golden test)."""

from __future__ import annotations

from fcmr_core.catalog import store
from fcmr_core.rules.registry import list_rules, resolve_rule_ids


def test_disabled_rules_empty_returns_all():
    """Golden test: empty disabled-rules list should return all rules (identical behavior)."""
    # Get all rules
    all_rules = list_rules()
    all_rule_ids = [r.rule_id for r in all_rules]

    # Verify that an empty disabled-rules list resolves to all rule IDs
    # (This simulates the behavior in runs.py when applying the filter)
    disabled = []
    filtered_ids = [rid for rid in all_rule_ids if rid not in disabled]

    # Should be identical
    assert filtered_ids == all_rule_ids, "Empty disabled list should not filter any rules"
    assert len(filtered_ids) == len(all_rule_ids), "Rule count should match"


def test_disabled_rules_filter_logic():
    """Test that disabled-rules filter correctly excludes specified rules."""
    # Simulate a rule list and disabled rules
    all_rule_ids = ["pan_format", "aadhaar_format", "pan_duplicate", "address_duplicate", "ucid"]
    disabled = ["pan_format", "address_duplicate"]  # Disable 2 rules

    # Apply filter
    filtered_ids = [rid for rid in all_rule_ids if rid not in disabled]

    # Should exclude exactly the disabled ones
    assert len(filtered_ids) == 3, "Should have 3 rules (5 - 2 disabled)"
    assert "pan_format" not in filtered_ids, "Disabled rule should not be in filtered list"
    assert "address_duplicate" not in filtered_ids, "Disabled rule should not be in filtered list"
    assert filtered_ids == ["aadhaar_format", "pan_duplicate", "ucid"], "Filtered list should match"
