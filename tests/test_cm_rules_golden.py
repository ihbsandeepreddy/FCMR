"""Customer Master rule-engine golden test.

Locks the deterministic output of the full 31-rule pipeline on a fixed synthetic
dataset (seed 42). Protects against silent behaviour changes during refactors
(e.g. vectorising the per-row rule loops): the produced exception status/code
counts must stay identical. If a rule's behaviour changes intentionally,
re-baseline EXPECTED_* in the same commit with a rationale.
"""

from __future__ import annotations

import random
import sys
import tempfile
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from generate_synthetic import generate  # noqa: E402

from fcmr_core.reporting.builder import build_exception_csvs  # noqa: E402
from fcmr_core.rules.registry import run_pipeline  # noqa: E402

EXPECTED_WIDE_ROWS = 200
EXPECTED_STATUS = {"ERROR": 4, "WARN": 196}
# DOB_AGE_OUT_OF_RANGE is intentionally excluded from the exact lock: it depends on
# date.today() (people cross the 18/65 boundaries over calendar time), so it would
# make this golden drift. It is asserted separately as "present and reasonable".
EXPECTED_CODES = {
    "AADHAAR_CHECKSUM_FAIL": 2,
    "ADDRESS_DUPLICATE": 36,
    "EMAIL_COMPANY_GENERIC_DOMAIN": 200,
    "PAN_INVALID_FORMAT": 1,
    "PIN_NOT_FOUND": 1,
    "STATE_PIN_MISMATCH": 1,
    "UCID_KYC_INCONSISTENT": 36,
}


def _run() -> tuple[dict, dict, int]:
    # generate_synthetic uses the global `random` for identity/DOB fields, so seed
    # it (in addition to its internal rng) for fully deterministic golden output.
    random.seed(42)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        csvp = td / "cm.csv"
        generate(200, csvp)
        cm = pl.read_csv(csvp, infer_schema_length=0)
        annotated = run_pipeline(cm)
        wide, long = build_exception_csvs(annotated, "golden-run", td)
        w = pl.read_csv(wide, infer_schema_length=0)
        lo = pl.read_csv(long, infer_schema_length=0)
        status = dict(sorted(w["overall_status"].value_counts().rows()))
        codes = dict(sorted(lo["exception_code"].value_counts().rows()))
        return status, codes, w.height


def test_cm_rules_output_is_stable():
    status, codes, wide_rows = _run()
    assert wide_rows == EXPECTED_WIDE_ROWS
    assert status == EXPECTED_STATUS, f"status counts changed: {status}"
    # Age code is date-sensitive: assert presence + sane range, then drop it.
    age_count = codes.pop("DOB_AGE_OUT_OF_RANGE", 0)
    assert 30 <= age_count <= 60, f"DOB_AGE_OUT_OF_RANGE unexpectedly {age_count}"
    assert codes == EXPECTED_CODES, f"exception code counts changed: {codes}"
