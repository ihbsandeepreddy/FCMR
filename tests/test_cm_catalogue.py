"""Tests for catalogue-grounded Customer Master forensic analytics.

Covers both the positive (detection) path and the NOT_RUN / no-detection path for
each of the 7 analytics in fcmr_core/analytics/cm_catalogue.py.
"""

from __future__ import annotations

import polars as pl

from fcmr_core.analytics import cm_catalogue as c


def _is_note(df: pl.DataFrame) -> bool:
    return "note" in df.columns


# --- CM-DQ-10 Address clustering -------------------------------------------


def test_address_clustering_flags_dense_address():
    df = pl.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(8)],
            "lan": [f"L{i}" for i in range(8)],
            "address_line1": ["DSA Office Plot 5"] * 7 + ["Genuine Home 12"],
            "city": ["Pune"] * 8,
            "pincode": ["411001"] * 8,
        }
    )
    res = c.generate_address_clustering(df, threshold=5)
    assert not _is_note(res)
    assert res.height == 1
    assert res[0, "Distinct Customers"] == 7
    assert res[0, "Risk"] == "HIGH"  # 7 not > 5*2=10, so HIGH (not CRITICAL)


def test_address_clustering_no_dense_address():
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "address_line1": ["Home A", "Home B"],
            "city": ["Pune", "Pune"],
        }
    )
    assert _is_note(c.generate_address_clustering(df))


def test_address_clustering_missing_column():
    df = pl.DataFrame({"customer_id": ["C1"]})
    assert _is_note(c.generate_address_clustering(df))


# --- CM-ID-01 Name similarity ----------------------------------------------


def test_name_similarity_detects_near_duplicates():
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "full_name": ["Rajesh Kumar", "Rajesh Kumarr", "Completely Different"],
            "pan": ["AAAAA1111A", "BBBBB2222B", "CCCCC3333C"],
            "pincode": ["411001", "411001", "411001"],
        }
    )
    res = c.generate_name_similarity_clusters(df, threshold=0.9)
    assert not _is_note(res)
    assert res.height >= 1
    assert res[0, "Similarity"] >= 0.9


def test_name_similarity_skips_same_pan():
    # Same name-ish but identical PAN -> not an identity-splitting signal
    df = pl.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "full_name": ["Rajesh Kumar", "Rajesh Kumarr"],
            "pan": ["AAAAA1111A", "AAAAA1111A"],
            "pincode": ["411001", "411001"],
        }
    )
    assert _is_note(c.generate_name_similarity_clusters(df, threshold=0.9))


def test_name_similarity_missing_column():
    assert _is_note(c.generate_name_similarity_clusters(pl.DataFrame({"customer_id": ["C1"]})))


# --- CM-ID-04 Email domain anomalies ---------------------------------------


def test_email_domain_flags_disposable_and_shared():
    df = pl.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(13)],
            "email": ["x@mailinator.com"] + [f"u{i}@shared.co" for i in range(12)],
        }
    )
    res = c.generate_email_domain_anomalies(df, shared_threshold=10)
    assert not _is_note(res)
    types = set(res["Anomaly Type"].to_list())
    assert "Disposable Domain" in types
    assert "Shared Domain" in types


def test_email_domain_clean():
    df = pl.DataFrame({"customer_id": ["C1", "C2"], "email": ["a@corp.com", "b@firm.in"]})
    assert _is_note(c.generate_email_domain_anomalies(df))


def test_email_domain_missing_column():
    assert _is_note(c.generate_email_domain_anomalies(pl.DataFrame({"customer_id": ["C1"]})))


# --- CM-DQ-06 Sequential KYC documents -------------------------------------


def test_sequential_kyc_detects_run():
    df = pl.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(4)],
            "pan": ["ABCDE1001A", "ABCDE1002A", "ABCDE1003A", "XYZAB9999Z"],
        }
    )
    res = c.generate_sequential_kyc_documents(df)
    assert not _is_note(res)
    assert res[0, "Document Type"] == "PAN"
    assert res[0, "Sequence Length"] == 3


def test_sequential_kyc_no_run():
    df = pl.DataFrame({"pan": ["ABCDE1001A", "ABCDE5005A", "ABCDE9009A"]})
    assert _is_note(c.generate_sequential_kyc_documents(df))


def test_sequential_kyc_no_columns():
    assert _is_note(c.generate_sequential_kyc_documents(pl.DataFrame({"customer_id": ["C1"]})))


# --- CM-DQ-07 Benford's Law ------------------------------------------------


def test_benford_runs_with_income():
    vals = []
    for d, n in [(1, 30), (2, 17), (3, 12), (4, 10), (5, 8), (6, 7), (7, 6), (8, 5), (9, 5)]:
        vals += [str(d * 10000 + i) for i in range(n)]
    df = pl.DataFrame({"income": vals})
    res = c.generate_income_benford(df)
    assert not _is_note(res)
    # last row carries the verdict, MAD row precedes it
    digits = res["Digit"].to_list()
    assert "MAD" in digits


def test_benford_not_run_without_income():
    assert _is_note(c.generate_income_benford(pl.DataFrame({"customer_id": ["C1"]})))


def test_benford_insufficient_sample():
    df = pl.DataFrame({"income": ["10000", "20000", "30000"]})
    assert _is_note(c.generate_income_benford(df))


# --- CM-DQ-09 Missing KYC by branch ----------------------------------------


def test_kyc_by_branch_flags_bad_branch():
    # 15 clean rows + 5 bad rows so the bad branch is well above 2x portfolio average.
    df = pl.DataFrame(
        {
            "branch_code": ["BR_GOOD"] * 15 + ["BR_BAD"] * 5,
            "pan": ["A"] * 15 + [None] * 5,
            "aadhaar": ["1"] * 15 + [None] * 5,
            "mobile": ["9"] * 20,
            "address_line1": ["addr"] * 20,
            "pincode": ["411001"] * 20,
        }
    )
    res = c.generate_kyc_completeness_by_branch(df)
    assert not _is_note(res)
    flags = dict(zip(res["Segment"].to_list(), res["Flag"].to_list()))
    assert flags.get("BR_BAD", "").startswith("FLAG")


def test_kyc_by_branch_not_run_without_segment():
    df = pl.DataFrame({"pan": ["A", None], "aadhaar": ["1", None]})
    assert _is_note(c.generate_kyc_completeness_by_branch(df))


# --- CM-ID-03 Onboarding velocity ------------------------------------------


def test_onboarding_velocity_detects_spike():
    # 20 quiet days (1 onboarding each) keep the std low, so one day of 10 stands out.
    dates = [f"2026-01-{d:02d}" for d in range(1, 21)] + ["2026-02-01"] * 10
    df = pl.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(len(dates))],
            "branch_code": ["BR1"] * len(dates),
            "onboarding_date": dates,
        }
    )
    res = c.generate_onboarding_velocity(df)
    assert not _is_note(res)
    assert res[0, "New Customers"] == 10


def test_onboarding_velocity_not_run_without_date():
    df = pl.DataFrame({"branch_code": ["BR1"], "customer_id": ["C1"]})
    assert _is_note(c.generate_onboarding_velocity(df))


def test_onboarding_velocity_not_run_without_segment():
    df = pl.DataFrame({"onboarding_date": ["2026-01-01"], "customer_id": ["C1"]})
    assert _is_note(c.generate_onboarding_velocity(df))


# --- Registry --------------------------------------------------------------


def test_registry_shape():
    assert len(c.CATALOGUE_ANALYTICS) == 7
    for key, title, cid, fn in c.CATALOGUE_ANALYTICS:
        assert isinstance(key, str) and key
        assert cid.startswith("CM-")
        assert callable(fn)
