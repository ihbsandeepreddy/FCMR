"""Upload and run tracking backed by DuckDB."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from fcmr_core.config import settings


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(settings.catalog_path))


def init_catalog() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                upload_id       TEXT PRIMARY KEY,
                report_type     TEXT NOT NULL,
                filename        TEXT NOT NULL,
                csv_path        TEXT,
                sniffed_headers TEXT,
                column_mapping  TEXT,
                row_count       INTEGER,
                parquet_path    TEXT,
                status          TEXT NOT NULL DEFAULT 'mapping_pending',
                created_at      TEXT NOT NULL
            )
        """)
        # Migrate existing tables that pre-date the column-mapping feature
        for col, dtype in [
            ("csv_path", "TEXT"),
            ("sniffed_headers", "TEXT"),
            ("column_mapping", "TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE uploads ADD COLUMN {col} {dtype}")
            except Exception:
                pass  # Column already exists

        con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id       TEXT PRIMARY KEY,
                upload_id    TEXT NOT NULL REFERENCES uploads(upload_id),
                status       TEXT NOT NULL DEFAULT 'pending',
                started_at   TEXT,
                finished_at  TEXT,
                wide_csv     TEXT,
                long_csv     TEXT,
                error        TEXT
            )
        """)


# ---------------------------------------------------------------------------
# Upload CRUD
# ---------------------------------------------------------------------------

def create_upload(report_type: str, filename: str) -> str:
    uid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO uploads (upload_id, report_type, filename, status, created_at) "
            "VALUES (?, ?, ?, 'mapping_pending', ?)",
            [uid, report_type, filename, _now()],
        )
    return uid


def set_mapping_pending(
    upload_id: str,
    *,
    csv_path: Path,
    sniffed_headers: list[str],
) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uploads SET csv_path=?, sniffed_headers=?, status='mapping_pending' WHERE upload_id=?",
            [str(csv_path), json.dumps(sniffed_headers), upload_id],
        )


def set_upload_ready(
    upload_id: str,
    *,
    parquet_path: Path,
    row_count: int,
    column_mapping: dict,
) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uploads SET parquet_path=?, row_count=?, column_mapping=?, status='ready' "
            "WHERE upload_id=?",
            [str(parquet_path), row_count, json.dumps(column_mapping), upload_id],
        )


def set_upload_failed(upload_id: str, *, error: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uploads SET status='failed' WHERE upload_id=?",
            [upload_id],
        )


def get_upload(upload_id: str) -> dict | None:
    with _conn() as con:
        rows = con.execute("SELECT * FROM uploads WHERE upload_id=?", [upload_id]).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def list_uploads() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM uploads ORDER BY created_at DESC").fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Run CRUD
# ---------------------------------------------------------------------------

def create_run(upload_id: str) -> str:
    rid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO runs (run_id, upload_id, status) VALUES (?, ?, 'pending')",
            [rid, upload_id],
        )
    return rid


def update_run(run_id: str, **kwargs: str | None) -> None:
    allowed = {"status", "started_at", "finished_at", "wide_csv", "long_csv", "error"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE runs SET {sets} WHERE run_id=?", [*fields.values(), run_id])


def list_runs(upload_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM runs WHERE upload_id=? ORDER BY run_id DESC", [upload_id]
        ).fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_run(run_id: str) -> dict | None:
    with _conn() as con:
        rows = con.execute("SELECT * FROM runs WHERE run_id=?", [run_id]).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
