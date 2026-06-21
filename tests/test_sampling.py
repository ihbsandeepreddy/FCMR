"""Sampling determinism + ICAI table (closes the documented coverage gap).

Locks the reproducibility invariant: same engagement_id:run_id ⇒ identical sample.
(The sample-size policy itself is slated for redesign; this determinism contract
must continue to hold afterwards.)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fcmr_core.sampling.icai_table import get_sample_size
from fcmr_core.sampling.sample import _make_seed, select_sample


def _wide_csv(path: Path, n: int = 60) -> None:
    lines = ["customer_id,overall_status,exception_codes,exception_descriptions"]
    for i in range(n):
        if i % 3 == 0:
            lines.append(f"C{i:04d},OK,,")
        elif i % 3 == 1:
            lines.append(f"C{i:04d},ERROR,PAN_DUPLICATE,dup")
        else:
            lines.append(f"C{i:04d},WARN,EMAIL_COMPANY_GENERIC_DOMAIN,generic")
    path.write_text("\n".join(lines) + "\n")


def test_seed_is_deterministic():
    assert _make_seed("eng", "run") == _make_seed("eng", "run")
    assert _make_seed("eng", "run1") != _make_seed("eng", "run2")


def test_sample_is_reproducible():
    with tempfile.TemporaryDirectory() as td:
        wide = Path(td) / "wide.csv"
        _wide_csv(wide)
        kw = dict(engagement_id="E1", run_id="R1", population=60, exception_count=40)
        s1 = select_sample(wide, **kw)
        s2 = select_sample(wide, **kw)
        assert [r["row_index"] for r in s1] == [r["row_index"] for r in s2]
        assert len(s1) > 0


def test_get_sample_size_bounds():
    # Within population, and never exceeds it.
    assert 0 < get_sample_size(1000, 50) <= 1000
    assert get_sample_size(10, 2) <= 10
