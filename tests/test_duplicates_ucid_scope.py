"""Regression test for UCID-scoped duplicate detection (C1 ordering fix).

Same-person / multiple-loan rows (same UCID, distinct LAN) that share an identity
key MUST be allowed (OK), not flagged as hard duplicates. This only works when the
`ucid` rule runs BEFORE the duplicate rules in the full pipeline. Before the fix,
`ucid` was registered/executed last, so the `ucid` column was absent when the
duplicate rules ran and every shared key was flagged ERROR.
"""

from __future__ import annotations

import polars as pl

from fcmr_core.rules.registry import run_pipeline


def _status_by_cid(annotated: pl.DataFrame, rule_id: str) -> dict[str, str]:
    col = f"_exc_{rule_id}_status"
    return dict(zip(annotated["customer_id"].to_list(), annotated[col].to_list()))


def test_shared_pan_same_person_distinct_lan_is_allowed():
    """Two loans for the same person (shared PAN ⇒ same UCID) with distinct LANs = OK."""
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4"],
            "full_name": ["Alice K", "Alice K", "Bob R", "Bob R"],
            "pan": ["ABCPK1234A", "ABCPK1234A", "XYZPB9999B", "XYZPB9999B"],
            # C1/C2 distinct LAN (legit multi-loan) ; C3/C4 SAME LAN (true duplicate)
            "lan": ["LN001", "LN002", "LN003", "LN003"],
        }
    )

    annotated = run_pipeline(df)

    # ucid must have run and grouped same-PAN rows together
    assert "ucid" in annotated.columns
    ucid_by_cid = dict(zip(annotated["customer_id"].to_list(), annotated["ucid"].to_list()))
    assert ucid_by_cid["C1"] == ucid_by_cid["C2"], "C1/C2 should share a UCID (shared PAN)"
    assert ucid_by_cid["C3"] == ucid_by_cid["C4"], "C3/C4 should share a UCID (shared PAN)"

    pan_status = _status_by_cid(annotated, "pan_duplicate")
    # Same UCID + distinct LAN ⇒ allowed
    assert pan_status["C1"] == "OK", pan_status
    assert pan_status["C2"] == "OK", pan_status
    # Same UCID + SAME LAN ⇒ flagged duplicate
    assert pan_status["C3"] == "ERROR", pan_status
    assert pan_status["C4"] == "ERROR", pan_status


def test_ucid_runs_before_duplicate_rules():
    """The execution order must place `ucid` before every `*_duplicate` rule."""
    from fcmr_core.rules.registry import _ensure_rules_loaded

    _ensure_rules_loaded()
    order: list[str] = []
    df = pl.DataFrame({"customer_id": ["C1"], "pan": ["ABCPK1234A"], "full_name": ["X"]})
    run_pipeline(df, on_progress=lambda c, t, rid: order.append(rid))

    ucid_idx = order.index("ucid")
    dup_indices = [i for i, r in enumerate(order) if r.endswith("_duplicate") and r != "ucid"]
    assert dup_indices, "expected duplicate rules in the pipeline"
    assert ucid_idx < min(dup_indices), f"ucid must precede duplicate rules; order={order}"
