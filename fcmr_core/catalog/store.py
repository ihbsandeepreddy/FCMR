"""Upload and run tracking backed by DuckDB."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from fcmr_core.config import apply_duckdb_limits, settings
from fcmr_core.logging_setup import get_logger

logger = get_logger("error")

# Single persistent connection to catalog.duckdb, shared across all threads in
# this process. DuckDB allows multiple cursors on one connection concurrently.
# A per-call duckdb.connect() to the same file from a second OS process (e.g.
# uvicorn --reload spawning a new worker while the old one hasn't exited yet)
# raises "file being used by another process". The persistent connection avoids
# that entirely — only one OS-level file handle is ever open.
_db_lock = threading.Lock()
_db_conn: duckdb.DuckDBPyConnection | None = None


def _conn() -> duckdb.DuckDBPyConnection:
    """Return a cursor on the shared persistent connection.

    Callers use ``with _conn() as con:`` — the cursor closes on __exit__ but
    the underlying file handle stays open, avoiding the OS file-lock that
    occurs when a new duckdb.connect() call races with an existing one from a
    reloading uvicorn worker.

    Connects with a bounded timeout (up to ~15 seconds total) to fail fast if
    the catalog is locked by another process, rather than hanging indefinitely.
    """
    global _db_conn
    with _db_lock:
        if _db_conn is None:
            # Bounded retry: up to 3 attempts, ~5 seconds apart
            last_error = None
            for attempt in range(3):
                try:
                    _db_conn = duckdb.connect(str(settings.catalog_path))
                    apply_duckdb_limits(_db_conn)
                    return _db_conn.cursor()
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        time.sleep(5)
            # All attempts failed
            error_msg = (
                f"catalog.duckdb is locked by another instance or inaccessible. "
                f"Close other copies of SanGir Automations and restart. "
                f"Error: {last_error}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from last_error
    return _db_conn.cursor()


def close_catalog() -> None:
    """Close the persistent catalog connection (graceful shutdown).

    Idempotent. Called on shutdown to release the DuckDB single-writer lock,
    allowing a new process to open the catalog without blocking.
    """
    global _db_conn
    with _db_lock:
        if _db_conn is not None:
            try:
                _db_conn.close()
            except Exception:
                pass
            _db_conn = None


def init_catalog() -> None:
    with _conn() as con:
        # Users table
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name  TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )
        """)

        # Engagements table
        con.execute("""
            CREATE TABLE IF NOT EXISTS engagements (
                engagement_id TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                client_name   TEXT,
                period_from   TEXT,
                period_to     TEXT,
                status        TEXT NOT NULL DEFAULT 'active',
                created_by    TEXT NOT NULL REFERENCES users(username),
                created_at    TEXT NOT NULL
            )
        """)

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
                engagement_id   TEXT REFERENCES engagements(engagement_id),
                created_at      TEXT NOT NULL
            )
        """)
        # Migrate existing tables that pre-date the column-mapping feature
        for col, dtype in [
            ("csv_path", "TEXT"),
            ("sniffed_headers", "TEXT"),
            ("column_mapping", "TEXT"),
            ("engagement_id", "TEXT"),
            ("batch_id", "TEXT"),
            ("ingested_at", "TEXT"),
            ("is_consolidated", "INTEGER DEFAULT 0"),
            ("source_count", "INTEGER"),
            ("source_files_json", "TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE uploads ADD COLUMN {col} {dtype}")
            except Exception:
                pass  # Column already exists

        # Consolidation batches — one row per multi-file upload awaiting / done
        # schema reconciliation.  status: reconcile_pending | consolidated | failed
        con.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                batch_id               TEXT PRIMARY KEY,
                report_type            TEXT NOT NULL,
                engagement_id          TEXT,
                status                 TEXT NOT NULL DEFAULT 'reconcile_pending',
                files_json             TEXT,
                consolidated_upload_id TEXT,
                created_at             TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id        TEXT PRIMARY KEY,
                upload_id     TEXT NOT NULL REFERENCES uploads(upload_id),
                engagement_id TEXT REFERENCES engagements(engagement_id),
                status        TEXT NOT NULL DEFAULT 'pending',
                started_at    TEXT,
                finished_at   TEXT,
                wide_csv      TEXT,
                long_csv      TEXT,
                error         TEXT
            )
        """)
        # Migrate runs table — additive only
        for col, dtype in [
            ("engagement_id", "TEXT"),
            ("workpaper_path", "TEXT"),
            ("progress_step", "TEXT"),
            ("progress_pct", "INTEGER"),
            ("selected_rules", "TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")
            except Exception:
                pass  # Column already exists

        # Create mapping_profiles table (Phase 3)
        con.execute("""
            CREATE TABLE IF NOT EXISTS mapping_profiles (
                profile_id      TEXT PRIMARY KEY,
                report_type     TEXT NOT NULL,
                header_signature TEXT NOT NULL,
                mapping_json    TEXT NOT NULL,
                engagement_id   TEXT,
                created_by      TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                UNIQUE (report_type, header_signature, engagement_id)
            )
        """)

        # Create settings table
        con.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key             TEXT PRIMARY KEY,
                value           TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)

        # EAD analytics runs (separate from KYC rules-based runs)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ead_runs (
                run_id        TEXT PRIMARY KEY,
                engagement_id TEXT REFERENCES engagements(engagement_id),
                status        TEXT NOT NULL DEFAULT 'pending',
                started_at    TEXT,
                finished_at   TEXT,
                output_dir    TEXT,
                error         TEXT,
                progress_step TEXT,
                progress_pct  INTEGER
            )
        """)

        # Create a default engagement for existing uploads
        try:
            con.execute(
                """
                INSERT INTO engagements (engagement_id, name, client_name, status, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                ["default", "Default Engagement", "Default", "active", "admin", _now()],
            )
        except Exception:
            pass  # Default engagement already exists

        # Backfill engagement_id for existing uploads
        con.execute("UPDATE uploads SET engagement_id = 'default' WHERE engagement_id IS NULL")
        con.execute("UPDATE runs SET engagement_id = 'default' WHERE engagement_id IS NULL")

        # Backfill batch_id and ingested_at for existing uploads (for consistency)
        con.execute("UPDATE uploads SET batch_id = 'legacy' WHERE batch_id IS NULL")
        con.execute("UPDATE uploads SET ingested_at = created_at WHERE ingested_at IS NULL")


# ---------------------------------------------------------------------------
# Upload CRUD
# ---------------------------------------------------------------------------


def create_upload(
    report_type: str,
    filename: str,
    batch_id: str | None = None,
    engagement_id: str | None = None,
) -> str:
    uid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO uploads (upload_id, report_type, filename, status, created_at, batch_id, engagement_id) "
            "VALUES (?, ?, ?, 'mapping_pending', ?, ?, ?)",
            [uid, report_type, filename, _now(), batch_id, engagement_id],
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
    batch_id: str | None = None,
    ingested_at: str | None = None,
) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE uploads SET parquet_path=?, row_count=?, column_mapping=?, batch_id=?, ingested_at=?, status='ready' "
            "WHERE upload_id=?",
            [
                str(parquet_path),
                row_count,
                json.dumps(column_mapping),
                batch_id,
                ingested_at,
                upload_id,
            ],
        )


def store_upload_data(upload_id: str, parquet_path: Path) -> None:
    """Import Parquet into DuckDB as a persistent table, then delete the file."""
    table = f"data_{upload_id.replace('-', '_')}"
    with _conn() as con:
        con.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT * FROM read_parquet('{parquet_path.as_posix()}')
        """)
    parquet_path.unlink(missing_ok=True)
    # Remove empty parent dir if present
    try:
        parquet_path.parent.rmdir()
    except Exception:
        pass


def get_upload_df(upload_id: str):
    """Return a Polars DataFrame for the upload's data from DuckDB."""

    table = f"data_{upload_id.replace('-', '_')}"
    with _conn() as con:
        return con.execute(f"SELECT * FROM {table}").pl()


def drop_upload_data(upload_id: str) -> None:
    """Remove the upload's data table from DuckDB (cleanup)."""
    table = f"data_{upload_id.replace('-', '_')}"
    with _conn() as con:
        con.execute(f"DROP TABLE IF EXISTS {table}")


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


def set_upload_consolidated_meta(
    upload_id: str,
    *,
    source_count: int,
    source_files: list[str],
) -> None:
    """Mark an upload as a consolidated source and record its origin files."""
    with _conn() as con:
        con.execute(
            "UPDATE uploads SET is_consolidated=1, source_count=?, source_files_json=? "
            "WHERE upload_id=?",
            [source_count, json.dumps(source_files), upload_id],
        )


# ---------------------------------------------------------------------------
# Consolidation batch CRUD
# ---------------------------------------------------------------------------


def create_batch(
    batch_id: str,
    report_type: str,
    *,
    engagement_id: str | None,
    files: list[dict],
) -> None:
    """Persist a multi-file batch awaiting schema reconciliation.

    ``files`` is a list of ``{"name", "path", "headers"}`` dicts (one per source CSV).
    """
    with _conn() as con:
        con.execute(
            "INSERT INTO batches (batch_id, report_type, engagement_id, status, files_json, created_at) "
            "VALUES (?, ?, ?, 'reconcile_pending', ?, ?)",
            [batch_id, report_type, engagement_id, json.dumps(files), _now()],
        )


def get_batch(batch_id: str) -> dict | None:
    with _conn() as con:
        rows = con.execute("SELECT * FROM batches WHERE batch_id=?", [batch_id]).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def set_batch_consolidated(batch_id: str, consolidated_upload_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE batches SET status='consolidated', consolidated_upload_id=? WHERE batch_id=?",
            [consolidated_upload_id, batch_id],
        )


# ---------------------------------------------------------------------------
# Run CRUD
# ---------------------------------------------------------------------------


def create_run(upload_id: str, engagement_id: str | None = None) -> str:
    rid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO runs (run_id, upload_id, engagement_id, status) VALUES (?, ?, ?, 'pending')",
            [rid, upload_id, engagement_id],
        )
    return rid


def update_run(run_id: str, **kwargs: str | None) -> None:
    allowed = {
        "status",
        "started_at",
        "finished_at",
        "wide_csv",
        "long_csv",
        "error",
        "workpaper_path",
        "progress_step",
        "progress_pct",
        "selected_rules",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE runs SET {sets} WHERE run_id=?", [*fields.values(), run_id])


def list_runs(upload_id: str, engagement_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if engagement_id:
            rows = con.execute(
                "SELECT * FROM runs WHERE upload_id=? AND engagement_id=? ORDER BY run_id DESC",
                [upload_id, engagement_id],
            ).fetchall()
        else:
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


def list_runs_for_engagement(engagement_id: str) -> list[dict]:
    """Return all runs for an engagement, joined with upload filename, newest first."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT r.*, u.filename, u.report_type, u.row_count
            FROM runs r
            LEFT JOIN uploads u ON r.upload_id = u.upload_id
            WHERE r.engagement_id = ?
            ORDER BY r.started_at DESC
            """,
            [engagement_id],
        ).fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, row)) for row in rows]


def get_run_summaries_by_upload(engagement_id: str) -> dict[str, dict]:
    """Return summaries of runs per upload: {upload_id: {"count": int, "last_status": str, "last_run_id": str, "last_finished": str}}.

    Only includes uploads that have at least one run.
    """
    try:
        with _conn() as con:
            rows = con.execute(
                """
                SELECT upload_id, COUNT(*) as count,
                       MAX(started_at) as last_started,
                       FIRST_VALUE(run_id) OVER (PARTITION BY upload_id ORDER BY started_at DESC) as last_run_id,
                       FIRST_VALUE(status) OVER (PARTITION BY upload_id ORDER BY started_at DESC) as last_status,
                       FIRST_VALUE(finished_at) OVER (PARTITION BY upload_id ORDER BY started_at DESC) as last_finished
                FROM runs
                WHERE engagement_id = ?
                GROUP BY upload_id
                """,
                [engagement_id],
            ).fetchall()
            cols = [d[0] for d in con.description]

        result = {}
        for row in rows:
            row_dict = dict(zip(cols, row))
            upload_id = row_dict["upload_id"]
            result[upload_id] = {
                "count": row_dict["count"],
                "last_status": row_dict["last_status"],
                "last_run_id": row_dict["last_run_id"],
                "last_finished": row_dict["last_finished"],
            }
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def create_user(username: str, password_hash: str, display_name: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
            [username, password_hash, display_name, _now()],
        )


def get_user(username: str) -> dict | None:
    with _conn() as con:
        rows = con.execute("SELECT * FROM users WHERE username=?", [username]).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def update_password(username: str, password_hash: str) -> None:
    """Update user password hash. Hash should be in 'salt:hash' format."""
    with _conn() as con:
        con.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            [password_hash, username],
        )


# ---------------------------------------------------------------------------
# Rule Configuration (per-engagement disabled rules)
# ---------------------------------------------------------------------------


def get_disabled_rules(engagement_id: str) -> list[str]:
    """Get list of disabled rule IDs for an engagement.

    Returns empty list if no rules are disabled (default: all enabled).
    """
    import json

    key = f"disabled_rules:{engagement_id}"
    setting = get_setting(key)
    if not setting or not setting.get("value"):
        return []
    try:
        return json.loads(setting["value"])
    except (json.JSONDecodeError, TypeError):
        return []


def set_disabled_rules(engagement_id: str, rule_ids: list[str]) -> None:
    """Set the list of disabled rule IDs for an engagement.

    Stores as JSON in the settings table with key 'disabled_rules:<engagement_id>'.
    Pass an empty list to enable all rules.
    """
    import json

    key = f"disabled_rules:{engagement_id}"
    value = json.dumps(rule_ids) if rule_ids else "[]"
    set_setting(key, value)


# ---------------------------------------------------------------------------
# Engagement CRUD
# ---------------------------------------------------------------------------


def create_engagement(
    name: str,
    client_name: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    created_by: str = "admin",
) -> str:
    eid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO engagements (engagement_id, name, client_name, period_from, period_to, status, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
            [eid, name, client_name, period_from, period_to, created_by, _now()],
        )
    return eid


def get_engagement(engagement_id: str) -> dict | None:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM engagements WHERE engagement_id=?", [engagement_id]
        ).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def list_engagements() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM engagements ORDER BY created_at DESC").fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def delete_upload(upload_id: str) -> None:
    """Delete an upload and its associated data table and runs."""
    with _conn() as con:
        # Collect run output dirs before deleting rows
        run_rows = con.execute(
            "SELECT wide_csv, long_csv, workpaper_path FROM runs WHERE upload_id=?", [upload_id]
        ).fetchall()
        con.execute("DELETE FROM runs WHERE upload_id=?", [upload_id])
        table_name = f"data_{upload_id.replace('-', '_')}"
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
        con.execute("DELETE FROM uploads WHERE upload_id=?", [upload_id])
    # Clean up output files on disk

    for row in run_rows:
        for path_str in row:
            if path_str:
                from pathlib import Path

                p = Path(path_str)
                p.unlink(missing_ok=True)
                try:
                    p.parent.rmdir()
                except Exception:
                    pass


def list_uploads(engagement_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if engagement_id:
            rows = con.execute(
                "SELECT * FROM uploads WHERE engagement_id=? ORDER BY created_at DESC",
                [engagement_id],
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM uploads ORDER BY created_at DESC").fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def save_mapping_profile(
    report_type: str,
    header_signature: str,
    mapping_json: str,
    engagement_id: str | None = None,
    created_by: str = "admin",
) -> str:
    """Save a column mapping profile. Returns profile_id. Updates existing profile if signature already saved."""
    profile_id = str(uuid.uuid4())
    with _conn() as con:
        try:
            con.execute(
                "INSERT INTO mapping_profiles (profile_id, report_type, header_signature, mapping_json, engagement_id, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    profile_id,
                    report_type,
                    header_signature,
                    mapping_json,
                    engagement_id,
                    created_by,
                    _now(),
                ],
            )
        except Exception:
            # Duplicate signature — update the mapping_json in place
            if engagement_id is None:
                con.execute(
                    "UPDATE mapping_profiles SET mapping_json=?, created_at=? "
                    "WHERE report_type=? AND header_signature=? AND engagement_id IS NULL",
                    [mapping_json, _now(), report_type, header_signature],
                )
            else:
                con.execute(
                    "UPDATE mapping_profiles SET mapping_json=?, created_at=? "
                    "WHERE report_type=? AND header_signature=? AND engagement_id=?",
                    [mapping_json, _now(), report_type, header_signature, engagement_id],
                )
    return profile_id


def find_profile_by_signature(
    report_type: str,
    header_signature: str,
    engagement_id: str | None = None,
) -> dict | None:
    """Find a mapping profile by report type and header signature."""
    with _conn() as con:
        if engagement_id is None:
            rows = con.execute(
                "SELECT * FROM mapping_profiles WHERE report_type=? AND header_signature=? AND engagement_id IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                [report_type, header_signature],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM mapping_profiles WHERE report_type=? AND header_signature=? AND engagement_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                [report_type, header_signature, engagement_id],
            ).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def list_profiles(report_type: str, engagement_id: str | None = None) -> list[dict]:
    """List mapping profiles for a report type."""
    with _conn() as con:
        if engagement_id:
            rows = con.execute(
                "SELECT * FROM mapping_profiles WHERE report_type=? AND engagement_id=? ORDER BY created_at DESC",
                [report_type, engagement_id],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM mapping_profiles WHERE report_type=? AND engagement_id IS NULL ORDER BY created_at DESC",
                [report_type],
            ).fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------


def get_setting(key: str) -> str | None:
    """Get a setting value by key."""
    with _conn() as con:
        rows = con.execute("SELECT value FROM settings WHERE key=?", [key]).fetchall()
        if not rows:
            return None
    return rows[0][0]


def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    with _conn() as con:
        con.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
            [key, value, _now(), value, _now()],
        )


def list_settings() -> dict[str, str]:
    """List all settings."""
    with _conn() as con:
        rows = con.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {row[0]: row[1] for row in rows}


def init_settings() -> None:
    """Initialize default settings if they don't exist."""
    from fcmr_core.config import settings as config_settings

    defaults = {
        "fuzzy_match_threshold": str(config_settings.fuzzy_match_threshold),
    }

    for key, value in defaults.items():
        if not get_setting(key):
            set_setting(key, value)


# ---------------------------------------------------------------------------
# EAD Run CRUD
# ---------------------------------------------------------------------------


def create_ead_run(engagement_id: str) -> str:
    rid = str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            "INSERT INTO ead_runs (run_id, engagement_id, status) VALUES (?, ?, 'pending')",
            [rid, engagement_id],
        )
    return rid


def update_ead_run(run_id: str, **kwargs) -> None:
    allowed = {
        "status",
        "started_at",
        "finished_at",
        "output_dir",
        "error",
        "progress_step",
        "progress_pct",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE ead_runs SET {sets} WHERE run_id=?", [*fields.values(), run_id])


def get_ead_run(run_id: str) -> dict | None:
    with _conn() as con:
        rows = con.execute("SELECT * FROM ead_runs WHERE run_id=?", [run_id]).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in con.description]
    return dict(zip(cols, rows[0]))


def list_ead_runs(engagement_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM ead_runs WHERE engagement_id=? ORDER BY started_at DESC NULLS LAST",
            [engagement_id],
        ).fetchall()
        cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def _now() -> str:
    return datetime.now(UTC).isoformat()
