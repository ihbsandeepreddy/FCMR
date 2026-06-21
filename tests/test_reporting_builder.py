"""Tests for exception CSV builder."""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl

from fcmr_core.reporting.builder import build_exception_csvs


def test_long_csv_has_customer_id():
    """Verify that customer_id is always present in long exception CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Create a minimal annotated frame with exceptions
        df = pl.DataFrame(
            {
                "_row_num": [1, 2, 3],
                "customer_id": ["C001", "C002", "C003"],
                "_exc_pan_format_status": ["OK", "ERROR", "OK"],
                "_exc_pan_format_code": ["", "PAN_INVALID_FORMAT", ""],
                "_exc_pan_format_desc": ["", "PAN format invalid", ""],
            }
        )

        wide_path, long_path = build_exception_csvs(df, "test_run", output_dir)

        # Read the long CSV and verify customer_id is present
        long_df = pl.read_csv(str(long_path))

        assert "customer_id" in long_df.columns, "customer_id missing from long CSV"
        assert len(long_df) > 0, "long CSV should have exception rows"
        # Row 2 had the exception
        assert long_df[0, "customer_id"] == "C002"


def test_long_csv_empty_has_customer_id_column():
    """Verify customer_id column exists even when no exceptions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Frame with no exceptions (all OK status)
        df = pl.DataFrame(
            {
                "_row_num": [1, 2],
                "customer_id": ["C001", "C002"],
                "_exc_pan_format_status": ["OK", "OK"],
                "_exc_pan_format_code": ["", ""],
                "_exc_pan_format_desc": ["", ""],
            }
        )

        wide_path, long_path = build_exception_csvs(df, "test_run", output_dir)

        # Read the long CSV
        long_df = pl.read_csv(str(long_path))

        # Even with no exceptions, customer_id column should exist
        assert "customer_id" in long_df.columns, "customer_id missing from long CSV"
