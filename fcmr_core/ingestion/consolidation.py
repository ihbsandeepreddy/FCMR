"""Ingest-time multi-file consolidation + schema reconciliation.

When several CSVs (or a folder / zip) are uploaded for one report type, this
module groups them by their header layout, proposes a unified column set with a
per-file alignment (exact then ``difflib`` fuzzy), and merges every file into a
single combined CSV via DuckDB.  That combined CSV is then fed into the normal
single-file ``ingest_csv`` → ``store_upload_data`` path, so the consolidated
batch becomes one ordinary upload (one ``data_<id>`` table) that the rest of the
app — column mapping, rules, downloads — sees with zero special-casing.

Deterministic by construction: no LLM, stdlib ``difflib`` only (invariant #1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import duckdb

from fcmr_core.catalog import store as catalog_store
from fcmr_core.config import apply_duckdb_limits, settings

# Internal column appended to every consolidated row to record its origin file.
SOURCE_COL = "_source_file"


@dataclass
class FileEntry:
    """One source file participating in a consolidation batch."""

    name: str
    path: str
    headers: list[str]

    def as_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "headers": self.headers}

    @classmethod
    def from_dict(cls, d: dict) -> FileEntry:
        return cls(name=d["name"], path=d["path"], headers=list(d.get("headers") or []))


def header_signature(headers: list[str]) -> str:
    """SHA256 over the sorted header list — same scheme as mapping profiles."""
    return hashlib.sha256(json.dumps(sorted(headers), sort_keys=True).encode()).hexdigest()


def _threshold() -> float:
    """Fuzzy-match threshold (DB-tunable, falls back to config default)."""
    raw = catalog_store.get_setting("fuzzy_match_threshold")
    try:
        return float(raw) if raw else settings.fuzzy_match_threshold
    except (ValueError, TypeError):
        return settings.fuzzy_match_threshold


def group_files_by_signature(files: list[FileEntry]) -> dict[str, dict]:
    """Group files that share an identical header layout.

    Returns an insertion-ordered ``{signature: {"headers": [...], "files": [FileEntry, ...]}}``.
    A single distinct signature means every file lines up already (no reconciliation needed).
    """
    groups: dict[str, dict] = {}
    for f in files:
        sig = header_signature(f.headers)
        if sig not in groups:
            groups[sig] = {"headers": list(f.headers), "files": []}
        groups[sig]["files"].append(f)
    return groups


def unified_columns(groups: dict[str, dict]) -> list[str]:
    """Union of all headers across groups, preserving first-seen order.

    De-duplicates case-insensitively: DuckDB treats column names as
    case-insensitive, so ``Covered_portion`` and ``covered_portion`` in the
    same SELECT would raise a BinderException.
    """
    seen: list[str] = []
    seen_lower: set[str] = set()
    for g in groups.values():
        for h in g["headers"]:
            if h.lower() not in seen_lower:
                seen.append(h)
                seen_lower.add(h.lower())
    return seen


def suggest_alignment(
    groups: dict[str, dict],
    unified_cols: list[str],
    threshold: float | None = None,
) -> dict[str, dict[str, str | None]]:
    """Propose, per group, which raw header feeds each unified column.

    Matching order per unified column: exact (case-insensitive), then best
    ``SequenceMatcher`` ratio ≥ ``threshold``.  Each raw header is used at most
    once per group; unmatched unified columns map to ``None`` (filled with NULL).
    """
    if threshold is None:
        threshold = _threshold()

    alignment: dict[str, dict[str, str | None]] = {}
    for sig, g in groups.items():
        headers: list[str] = g["headers"]
        lower_index = {h.lower(): h for h in headers}
        used: set[str] = set()
        col_map: dict[str, str | None] = {}

        for uc in unified_cols:
            # Exact (case-insensitive) match first.
            cand = lower_index.get(uc.lower())
            if cand is not None and cand not in used:
                col_map[uc] = cand
                used.add(cand)
                continue

            # Fuzzy fallback.
            best: str | None = None
            best_score = 0.0
            for h in headers:
                if h in used:
                    continue
                score = SequenceMatcher(None, uc.lower(), h.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best = h
            if best is not None and best_score >= threshold:
                col_map[uc] = best
                used.add(best)
            else:
                col_map[uc] = None
        alignment[sig] = col_map
    return alignment


def build_combined_csv(
    ordered_groups: list[tuple[str, dict]],
    alignment: dict[str, dict[str, str | None]],
    unified_cols: list[str],
    out_path: Path,
) -> int:
    """Merge every file in every group into one CSV at ``out_path``.

    Each file is projected onto ``unified_cols`` using its group's alignment
    (raw header → unified, or ``NULL`` when unaligned), tagged with a
    ``_source_file`` column, and ``UNION ALL BY NAME``-stacked.  ``all_varchar``
    avoids cross-file type clashes at merge time; ``ingest_csv`` re-infers types
    afterwards.  Returns the combined row count.
    """
    selects: list[str] = []
    for sig, g in ordered_groups:
        col_map = alignment.get(sig, {})
        for f in g["files"]:
            parts: list[str] = []
            for uc in unified_cols:
                safe_uc = uc.replace('"', '""')
                raw = col_map.get(uc)
                if raw:
                    safe_raw = raw.replace('"', '""')
                    parts.append(f'"{safe_raw}" AS "{safe_uc}"')
                else:
                    parts.append(f'NULL AS "{safe_uc}"')
            safe_name = f.name.replace("'", "''")
            src_path = Path(f.path).as_posix()
            selects.append(
                f"SELECT {', '.join(parts)}, '{safe_name}' AS \"{SOURCE_COL}\" "
                f"FROM read_csv('{src_path}', auto_detect=true, ignore_errors=true, "
                f"all_varchar=true, strict_mode=false)"
            )

    union_sql = "\nUNION ALL BY NAME\n".join(selects)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect() as con:
        apply_duckdb_limits(con)
        con.execute(f"COPY ({union_sql}) TO '{out_path.as_posix()}' (HEADER, FORMAT CSV)")
        n: int = con.execute(
            f"SELECT COUNT(*) FROM read_csv('{out_path.as_posix()}', "
            f"auto_detect=true, ignore_errors=true, all_varchar=true)"
        ).fetchone()[
            0
        ]  # type: ignore[index]
    return n
