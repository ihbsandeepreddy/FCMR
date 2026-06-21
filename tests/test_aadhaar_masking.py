"""Aadhaar masking in the downloadable wide CSV (privacy invariant #2)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import polars as pl

from fcmr_core.reporting.builder import build_exception_csvs
from fcmr_core.rules.registry import run_pipeline


def test_wide_csv_masks_aadhaar():
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "full_name": ["Alice", "Bob"],
            "aadhaar": ["123456789012", "999988887777"],
            "lan": ["LN1", "LN2"],
        }
    )
    annotated = run_pipeline(df, rule_ids=["aadhaar_format"])
    with tempfile.TemporaryDirectory() as td:
        wide, _ = build_exception_csvs(annotated, "mask-run", Path(td))
        text = Path(wide).read_text()

    # No raw 12-digit Aadhaar may appear anywhere in the output.
    assert not re.search(r"\b\d{12}\b", text), "raw Aadhaar leaked into wide CSV"
    # Masked form must be present (XXXXXXXX + last 4).
    assert "XXXXXXXX9012" in text
    assert "XXXXXXXX7777" in text
