#!/usr/bin/env python3
"""Quick test of audit sampling engine."""

from fcmr_core.sampling.audit_sample_engine import (
    generate_synthetic_loan_master,
    run_audit_sampling,
)

print("Testing audit sampling engine with 100K rows...")
df = generate_synthetic_loan_master(100_000)
sample, summary = run_audit_sampling(df)

print(f"\nResults:")
print(f"  Population: {summary['population_total']:,}")
print(f"  Clean: {summary['clean_records']:,}")
print(f"  Exceptions: {summary['exception_records']:,}")
print(f"  Sample: {summary['total_sample_size']:,} ({summary['sample_pct']:.2f}%)")
print(f"    - Exceptions: {summary['exceptions_sampled']}")
print(f"    - Strata: {summary['strata_coverage_sampled']}")
print(f"    - Random: {summary['random_sampled']}")
print("\n[OK] Engine works!")
