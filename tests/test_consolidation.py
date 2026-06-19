"""Tests for ingest-time multi-file consolidation + schema reconciliation."""

from __future__ import annotations

import polars as pl

from fcmr_core.ingestion.consolidation import (
    SOURCE_COL,
    FileEntry,
    build_combined_csv,
    group_files_by_signature,
    suggest_alignment,
    unified_columns,
)


def _write_csv(path, headers, rows):
    lines = [",".join(headers)]
    lines += [",".join(str(c) for c in r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_group_same_headers_collapse_to_one_group(tmp_path):
    a = FileEntry("a.csv", str(tmp_path / "a.csv"), ["id", "name"])
    b = FileEntry("b.csv", str(tmp_path / "b.csv"), ["name", "id"])  # order-insensitive
    groups = group_files_by_signature([a, b])
    assert len(groups) == 1
    assert len(next(iter(groups.values()))["files"]) == 2


def test_group_mixed_headers_split(tmp_path):
    a = FileEntry("a.csv", str(tmp_path / "a.csv"), ["id", "name"])
    b = FileEntry("b.csv", str(tmp_path / "b.csv"), ["id", "full_name"])
    groups = group_files_by_signature([a, b])
    assert len(groups) == 2


def test_unified_columns_union_first_seen_order():
    groups = {
        "s1": {"headers": ["id", "name"], "files": []},
        "s2": {"headers": ["id", "email"], "files": []},
    }
    assert unified_columns(groups) == ["id", "name", "email"]


def test_suggest_alignment_exact_and_fuzzy():
    groups = {
        "s1": {"headers": ["id", "name"], "files": []},
        "s2": {"headers": ["id", "naam"], "files": []},
    }
    unified = unified_columns(groups)  # id, name, naam
    align = suggest_alignment(groups, unified, threshold=0.6)
    # exact match within its own group
    assert align["s1"]["id"] == "id"
    assert align["s1"]["name"] == "name"
    # 'naam' fuzzily matches the unified 'name' column in group s2
    assert align["s2"]["name"] == "naam"
    # a column absent from a group with no fuzzy hit stays None
    assert align["s1"]["naam"] is None


def test_build_combined_csv_merges_and_tags_source(tmp_path):
    fa = _write_csv(tmp_path / "a.csv", ["id", "name"], [(1, "Asha"), (2, "Bala")])
    fb = _write_csv(tmp_path / "b.csv", ["id", "full_name"], [(3, "Chen")])

    a = FileEntry("a.csv", str(fa), ["id", "name"])
    b = FileEntry("b.csv", str(fb), ["id", "full_name"])
    groups = group_files_by_signature([a, b])
    ordered = list(groups.items())
    unified = unified_columns(groups)  # id, name, full_name
    align = suggest_alignment(groups, unified, threshold=0.95)

    out = tmp_path / "combined.csv"
    n = build_combined_csv(ordered, align, unified, out)

    assert n == 3
    df = pl.read_csv(out)
    # unified columns + the source tag
    assert set(unified).issubset(set(df.columns))
    assert SOURCE_COL in df.columns
    assert set(df[SOURCE_COL].to_list()) == {"a.csv", "b.csv"}
    # b.csv has no 'name' value → NULL/empty for that row
    bala = df.filter(pl.col(SOURCE_COL) == "a.csv")
    assert "Asha" in bala["name"].to_list()
