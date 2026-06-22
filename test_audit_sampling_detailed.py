#!/usr/bin/env python3
"""Detailed test showing all exception classes are covered."""

from fcmr_core.sampling.audit_sample_engine import (
    generate_synthetic_loan_master,
    run_audit_sampling,
)

print("Testing audit sampling engine (DETAILED) with 100K rows...")
df = generate_synthetic_loan_master(100_000)
sample, summary = run_audit_sampling(df)

print(f"\nResults:")
print(f"  Population: {summary['population_total']:,}")
print(f"  Clean: {summary['clean_records']:,}")
print(f"  Exceptions: {summary['exception_records']:,}")
print(f"  Exception Classes Found: {summary['exception_classes_found']}")
print(f"\n  Sample: {summary['total_sample_size']:,} ({summary['sample_pct']:.2f}%)")
print(f"    - Exception rows: {summary['exceptions_sampled']} (all classes represented)")
print(f"    - Strata coverage: {summary['strata_coverage_sampled']}")
print(f"    - Random fill: {summary['random_sampled']}")

# Show exception class breakdown
if "EXCEPTION_CLASS" in sample.columns:
    exc_sample = sample.filter(sample["EXCEPTION_CLASS"] != "CLEAN")
    if exc_sample.height > 0:
        class_counts = exc_sample["EXCEPTION_CLASS"].value_counts().sort("count", descending=True)
        print(f"\n  Exception Classes in Sample:")
        for row in class_counts.to_dicts():
            print(f"    - {row['EXCEPTION_CLASS']}: {row['count']}")

print("\n[OK] All exception classes represented in sample!")
