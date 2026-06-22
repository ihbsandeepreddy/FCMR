#!/usr/bin/env python3
"""CLI for NBFC Audit Sampling Engine - handles 10M transaction portfolios."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fcmr_core.sampling.audit_sample_engine import (
    _generate_synthetic_loan_master,
    export_to_excel,
    run_audit_sampling,
)

OUTPUT_DIR = Path("outputs/audit_sampling")


def main(n_rows: int = 10_000_000):
    """Generate synthetic data, run sampling, export to Excel."""
    print(f"\n{'='*70}")
    print(f"NBFC Audit Sampling Engine - {n_rows:,} Transaction Portfolio")
    print(f"{'='*70}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate synthetic data
    print(f"[1/4] Generating {n_rows:,} synthetic loan records...")
    start = time.time()
    df = _generate_synthetic_loan_master(n_rows)
    print(f"      ✅ Done in {time.time() - start:.1f}s | {len(df):,} rows")

    # Step 2: Run sampling engine
    print(f"\n[2/4] Detecting exceptions & running audit sampling...")
    start = time.time()
    selected_sample, summary = run_audit_sampling(df)
    elapsed = time.time() - start
    print(f"      ✅ Done in {elapsed:.1f}s")

    # Step 3: Display summary
    print(f"\n[3/4] Summary Statistics:")
    print(f"      {summary['population_total']:,} total records")
    print(f"      {summary['clean_records']:,} clean ({summary['clean_records']/summary['population_total']*100:.1f}%)")
    print(f"      {summary['exception_records']:,} exceptions ({summary['exception_records']/summary['population_total']*100:.1f}%)")
    print(f"      ")
    print(f"      SAMPLE COMPOSITION:")
    print(f"      - {summary['exceptions_sampled']} exception rows (all classes)")
    print(f"      - {summary['strata_coverage_sampled']} strata coverage rows")
    print(f"      - {summary['random_sampled']} random weighted rows")
    print(f"      ────────────────────────")
    print(f"      {summary['total_sample_size']:,} TOTAL SELECTED ({summary['sample_pct']:.2f}% of portfolio)")

    # Step 4: Export to Excel
    print(f"\n[4/4] Exporting to Excel workbook...")
    start = time.time()
    output_file = OUTPUT_DIR / f"audit_sample_{n_rows//1_000_000}M.xlsx"
    export_to_excel(selected_sample, summary, output_file)
    print(f"      ✅ Done in {time.time() - start:.1f}s")

    print(f"\n{'='*70}")
    print(f"✅ COMPLETE\n")
    print(f"Output: {output_file.resolve()}\n")
    return selected_sample, summary


if __name__ == "__main__":
    # Parse CLI args
    n_rows = 10_000_000
    if len(sys.argv) > 1:
        try:
            n_rows = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python audit_sampling_cli.py [n_rows (default 10000000)]")
            sys.exit(1)

    main(n_rows)
