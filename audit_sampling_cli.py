#!/usr/bin/env python3
"""CLI for NBFC Audit Sampling Engine — handles 10M-row portfolios."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fcmr_core.sampling.audit_sample_engine import (
    export_to_excel,
    generate_synthetic_loan_master,
    run_audit_sampling,
)

OUTPUT_DIR = Path("outputs/audit_sampling")


def main(n_rows: int = 10_000_000) -> None:
    print(f"\n{'='*70}")
    print(f"NBFC Audit Sampling Engine  |  {n_rows:,} row portfolio")
    print(f"{'='*70}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/4] Generating {n_rows:,} synthetic loan records...")
    t0 = time.time()
    df = generate_synthetic_loan_master(n_rows)
    print(f"      done in {time.time()-t0:.1f}s  |  {len(df):,} rows")

    print(f"\n[2/4] Detecting exceptions & running audit sampling (seed={42})...")
    t0 = time.time()
    selected, summary = run_audit_sampling(df)
    print(f"      done in {time.time()-t0:.1f}s")

    print(f"\n[3/4] Summary")
    print(f"      population : {summary['population_total']:>12,}")
    print(f"      clean      : {summary['clean_records']:>12,}  ({summary['clean_records']/summary['population_total']*100:.1f} %)")
    print(f"      exceptions : {summary['exception_records']:>12,}  ({summary['exception_records']/summary['population_total']*100:.1f} %)")
    print(f"      exc classes found/sampled: "
          f"{summary['exception_classes_found']} / {summary['exception_classes_sampled']}")
    print()
    print(f"      SAMPLE COMPOSITION:")
    print(f"        exceptions (all classes) : {summary['exceptions_sampled']:>6}")
    print(f"        strata coverage          : {summary['strata_covered']:>6}")
    print(f"        random fill              : {summary['random_sampled']:>6}")
    print(f"        ─────────────────────────────")
    print(f"        TOTAL                    : {summary['total_sample_size']:>6}  ({summary['sample_pct']:.3f} %)")
    print()
    print(f"      Per-class breakdown:")
    for rule, counts in summary["per_class"].items():
        if counts["found"] > 0:
            print(f"        {rule:<38}  found={counts['found']:>8,}  sampled={counts['sampled']}")
    print()
    print(f"      Recency basis: {summary['recency_basis']}")
    for note in summary["assumptions"]:
        print(f"      Note: {note}")

    print(f"\n[4/4] Exporting to Excel...")
    t0 = time.time()
    out = OUTPUT_DIR / f"audit_sample_{n_rows:_}.xlsx"
    export_to_excel(selected, summary, out)
    print(f"      done in {time.time()-t0:.1f}s")

    print(f"\n{'='*70}")
    print(f"Output: {out.resolve()}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    n_rows = 10_000_000
    if len(sys.argv) > 1:
        try:
            n_rows = int(sys.argv[1])
        except ValueError:
            print("Usage: python audit_sampling_cli.py [n_rows]")
            sys.exit(1)
    main(n_rows)
