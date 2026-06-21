"""EAD baseline golden test — locks the FROZEN EAD engine's output.

The EAD module is a frozen baseline (CLAUDE.md / project decision): shared-utility
work elsewhere must never silently change EAD report outputs. This test runs the EAD
engine on a fixed, deterministic frame and asserts the produced report set and each
report's (columns, row-count) are unchanged. If an intentional, signed-off EAD change
is made, re-baseline the EXPECTED dict in the same commit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl

from fcmr_core.analytics import ead_analytics as ea


def _ead_frame() -> pl.DataFrame:
    n = 18
    return pl.DataFrame(
        {
            "loan_id": [f"L{i:04d}" for i in range(n)],
            "scheme_id": ["S1", "S2", "S3"] * (n // 3),
            "scheme_name": ["Home", "Auto", "LAP"] * (n // 3),
            "sbu": ["Retail", "SME", "Retail"] * (n // 3),
            "sub_sbu": ["A", "B", "A"] * (n // 3),
            "state": ["KA", "MH", "TN"] * (n // 3),
            "loan_status": ["Active"] * (n - 2) + ["Closed", "Closed"],
            "stage": ["Stage 1", "Stage 2", "Stage 3"] * (n // 3),
            "dpd_bucket": ["0-30", "31-60", "91-120", "NPA", "0-30", "61-90"] * (n // 6),
            "ead": [85000.0 + i * 500 for i in range(n)],
            "outstanding_principal": [80000.0 + i * 500 for i in range(n)],
            "sanction_amount": [100000.0 + i * 1000 for i in range(n)],
            "disbursed_amount": [90000.0 + i * 1000 for i in range(n)],
            "collateral_value": [70000.0 + i * 400 for i in range(n)],
            "covered_portion": [60000.0 + i * 300 for i in range(n)],
            "uncovered_portion": [10000.0 + i * 100 for i in range(n)],
            "existing_provision": [2000.0 + i * 50 for i in range(n)],
            "additional_provision": [500.0 + i * 10 for i in range(n)],
            "total_provision": [2500.0 + i * 60 for i in range(n)],
            "written_off": ["No"] * (n - 1) + ["Yes"],
        }
    )


# Locked baseline captured from the current EAD engine (frozen).
EXPECTED: dict[str, dict] = {
    "dpd_summary": {
        "columns": [
            "DPD Bucket",
            "Loan Count",
            "Total EAD",
            "Outstanding Principal",
            "Total Provision",
        ],
        "rows": 5,
    },
    "fvtpl": {"columns": ["note"], "rows": 1},
    "geographic": {
        "columns": ["State", "Total EAD", "Total Provision", "Loan Count"],
        "rows": 3,
    },
    "negative_check": {
        "columns": ["Column", "Total Rows", "Negative Count", "Null Count", "Has Issue"],
        "rows": 10,
    },
    "pivot": {
        "columns": [
            "scheme_id",
            "scheme_name",
            "state",
            "sbu",
            "sub_sbu",
            "loan_status",
            "stage",
            "dpd_bucket",
            "written_off",
            "Sum(DrsPOS)",
            "Sum(EAD)",
            "Sum(National_Asset_Value)",
            "Sum(Covered_Portion)",
            "Sum(Uncovered_Portion)",
            "Sum(Provsion_as_per_Policy)",
            "Sum(AdditionalProvision)",
            "Sum(Total_Provision)",
            "Sum(SANCTIONAMOUNT)",
            "Sum(DISBURSEDAMOUNT)",
            "Count(AGREEMENTID_R)",
        ],
        "rows": 8,
    },
    "provision_check": {
        "columns": [
            "Loan ID",
            "Stage",
            "DPD Bucket",
            "EAD",
            "Additional Provision",
            "Policy Provision",
            "Ratio (Addl/Policy)",
            "Outlier Flag",
        ],
        "rows": 18,
    },
    "security": {
        "columns": [
            "Stage",
            "Covered (Secured)",
            "Uncovered (Unsecured)",
            "Total EAD",
            "Security Coverage %",
        ],
        "rows": 3,
    },
    "stage_dpd": {
        "columns": ["Stage", "DPD Bucket", "Loan Count", "Total EAD", "DPD-Stage Mismatch Flag"],
        "rows": 6,
    },
    "stage_mismatch": {"columns": ["note"], "rows": 1},
    "stage_summary": {
        "columns": [
            "stage",
            "Total EAD",
            "Total Provision",
            "Provision as per Policy",
            "Additional Provision",
            "Loan Count",
            "Coverage %",
        ],
        "rows": 3,
    },
    "writeoff": {
        "columns": ["written_off", "stage", "Total EAD", "Total Provision", "Loan Count"],
        "rows": 4,
    },
}


def test_ead_baseline_unchanged():
    df = _ead_frame()
    with tempfile.TemporaryDirectory() as td:
        paths = ea.run_ead_analytics(df, Path(td))
        produced = {}
        for key, p in paths.items():
            if str(p).endswith(".csv"):
                d = pl.read_csv(p, infer_schema_length=0)
                produced[key] = {"columns": list(d.columns), "rows": d.height}

    assert set(produced) == set(EXPECTED), (
        f"EAD report set changed.\n  added: {set(produced) - set(EXPECTED)}\n"
        f"  removed: {set(EXPECTED) - set(produced)}"
    )
    for key, exp in EXPECTED.items():
        assert produced[key] == exp, f"EAD report '{key}' changed: {produced[key]} != {exp}"
