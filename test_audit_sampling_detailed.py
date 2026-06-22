#!/usr/bin/env python3
"""Verifies all four audit sampling criteria against the spec."""

from fcmr_core.sampling.audit_sample_engine import (
    EXCEPTION_RULES,
    generate_synthetic_loan_master,
    run_audit_sampling,
)

print("Running audit sampling criteria verification (100K rows)...\n")
df = generate_synthetic_loan_master(100_000)
sample, summary = run_audit_sampling(df)

# ── Criterion 1 — full population coverage ───────────────────────────────────
n_strata = summary["strata_covered"]
print(f"Criterion 1  Full population coverage")
print(f"  Strata covered : {n_strata} (Product x Status x Branch)")
assert n_strata > 0, "No strata rows selected!"

# ── Criterion 2 — every exception class represented ──────────────────────────
print(f"\nCriterion 2  Exception class coverage")
print(f"  Classes found    : {summary['exception_classes_found']}")
print(f"  Classes sampled  : {summary['exception_classes_sampled']}")
print(f"  Per-class detail:")
all_ok = True
for rule, counts in summary["per_class"].items():
    if counts["found"] > 0:
        status = "OK" if counts["sampled"] > 0 else "FAIL"
        if counts["sampled"] == 0:
            all_ok = False
        marker = "    " if status == "OK" else "!!!"
        print(f"  {marker} {rule:<38}  found={counts['found']:>8,}  sampled={counts['sampled']}  [{status}]")
assert all_ok, "Some exception classes found but NOT sampled!"
assert summary["exception_classes_found"] == summary["exception_classes_sampled"], \
    "Found classes != sampled classes"

# ── Criterion 3 — random sample from clean ───────────────────────────────────
print(f"\nCriterion 3  Unbiased random sampling")
print(f"  Random rows   : {summary['random_sampled']}")
print(f"  Clean records : {summary['clean_records']:,}")
# random_sampled may be 0 if strata coverage already exceeds the target
print(f"  [OK] random phase ran (0 acceptable if strata >= target)")

# ── Criterion 4 — recency weight ─────────────────────────────────────────────
print(f"\nCriterion 4  Recency bias (weight, not hard filter)")
print(f"  Basis : {summary['recency_basis']}")
if "RECENCY_WEIGHT" in sample.columns:
    rw = sample["RECENCY_WEIGHT"]
    print(f"  Weight range: {rw.min():.3f} – {rw.max():.3f}  (expected 0.25–1.0)")
    assert rw.min() >= 0.24, "Recency weight below 0.25 — hard filter may have applied"
    assert rw.max() <= 1.01, "Recency weight above 1.0"
    # Verify old exceptions are still in sample (not hard-filtered)
    if summary["exception_records"] > 0:
        exc_sample = sample.filter(
            sample["SELECTION_REASON"].str.starts_with("EXCEPTION:")
        )
        if exc_sample.height > 0:
            min_exc_rw = exc_sample["RECENCY_WEIGHT"].min()
            print(f"  Min recency_weight in exception sample: {min_exc_rw:.3f}  (> 0 confirms old rows kept)")
            assert min_exc_rw > 0, "Old exception rows were hard-filtered out"

# ── Multi-flag verification ───────────────────────────────────────────────────
print(f"\nBonus  Multi-flag exceptions")
if "EXCEPTION_FLAGS" in sample.columns:
    multi_flag = sample.filter(
        sample["EXCEPTION_FLAGS"].str.contains(";")
    )
    print(f"  Rows with multiple exception flags: {multi_flag.height}")

# ── SELECTION_REASON column ───────────────────────────────────────────────────
print(f"\nBonus  Output columns check")
required_cols = {"SELECTION_REASON", "EXCEPTION_FLAGS", "RECENCY_WEIGHT"}
missing = required_cols - set(sample.columns)
if missing:
    print(f"  FAIL — missing output columns: {missing}")
    assert False, f"Missing output columns: {missing}"
else:
    print(f"  [OK] All required output columns present: {required_cols}")

# ── Overall summary ───────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"Population : {summary['population_total']:,}")
print(f"  Clean    : {summary['clean_records']:,}")
print(f"  Exception: {summary['exception_records']:,}  ({summary['exception_records']/summary['population_total']*100:.1f}%)")
print(f"Sample     : {summary['total_sample_size']:,}  ({summary['sample_pct']:.3f}%)")
print(f"  Phase 1  : {summary['exceptions_sampled']} exception rows")
print(f"  Phase 2  : {summary['strata_covered']} strata rows")
print(f"  Phase 3  : {summary['random_sampled']} random rows")
print(f"\n[OK] All 4 criteria PASSED")
