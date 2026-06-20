# SanGir Automations — Troubleshooting Guide

This document covers common issues, their root causes, and fixes. It is the authoritative
reference for debugging and should be consulted before filing issues.

---

## "Runs don't show up in Data Analytics (`/runs`)"

### Symptom
You create an upload, map columns to ready, run analytics via `/runs/start` or the upload
detail "Run Analytics" button, but the run never appears in the Data Analytics runs list.
The run *does* exist in the database (visible via DB query), but the `/runs` page shows
an empty list.

### Root Cause (v0.1.29 bug, fixed in v0.1.30)
The `create_run()` function did not store the `engagement_id` with each run. The `/runs`
list queries only runs **scoped to the active engagement** (`WHERE engagement_id = ?`), so
runs with `engagement_id=NULL` were silently hidden.

### Fix (v0.1.30+)
Upgrade to v0.1.30 or later. The fix:
- `create_run()` now accepts and stores `engagement_id` parameter.
- Both start endpoints (`POST /runs/start` and `POST /uploads/{id}/run`) now pass
  `engagement_id` from the session.
- All new runs are properly scoped and visible in the Data Analytics list.

### Manual Recovery (v0.1.29 only)
If you must stay on v0.1.29 and need to see a run:
1. Open the catalog via a tool like DuckDB CLI or a DB browser.
2. Run: `UPDATE runs SET engagement_id = 'default' WHERE engagement_id IS NULL;`
3. Refresh the `/runs` page.

**Note:** This workaround is temporary. Upgrade to v0.1.30 as soon as possible.

---

## "Run shows 'All Categories' despite selecting some"

### Symptom
You select specific categories (e.g., "KYC Format", "Duplicates"), click "Run Selected",
and the run completes. But when you view the run detail, the header says "All Categories"
instead of listing the selected ones.

### Root Cause (v0.1.29 bug, fixed in v0.1.30)
The `selected_rules` field existed in the database schema and was being read by the
run-detail handler, but **nothing was writing it**. The start endpoints resolved categories
to rule IDs but never persisted them, so the run-detail page had no way to know which
categories were chosen.

### Fix (v0.1.30+)
Upgrade to v0.1.30 or later. The fix:
- Both start endpoints now call `store.update_run(run_id, selected_rules=json.dumps(rule_ids))`
  when `mode != "all"`.
- The `run_detail()` handler reads `selected_rules`, deserializes the JSON, and displays the
  correct category labels.

---

## "Large file fails: OutOfMemoryException / MemoryError"

### Symptom
You upload a large CSV (e.g., 9+ million rows), map columns, and start a run. The run
fails immediately with:
```
OutOfMemoryException
```
or
```
MemoryError
```

in the processing log (`data/logs/processing.log`).

The error happens **during ingestion**, before any rules are run.

### Root Cause (v0.1.29 bug, CRITICAL, fixed in v0.1.30)
The ingestion pipeline opens a DuckDB connection (`duckdb.connect()`) to stream the CSV
into Parquet **without calling `apply_duckdb_limits(con)`**. This means DuckDB has no
memory cap and will attempt to buffer the entire file in RAM, causing OOM on large files.

Every other analytics connection in the codebase calls `apply_duckdb_limits()`:
- Catalog store (`store.py:37`) ✓
- Duplicate detection (`duplicates.py:86`) ✓
- Consolidation (`consolidation.py:172`) ✓
- **Ingestion pipeline (`pipeline.py:129`) ✗ — MISSING (fixed in v0.1.30)**

### Fix (v0.1.30+)
Upgrade to v0.1.30 or later. The fix adds the missing `apply_duckdb_limits(con)` call
immediately after opening the connection in `_stream_to_parquet()`.

### Workaround (v0.1.29 only)
If you must stay on v0.1.29:

1. **Reduce the DuckDB memory limit** before uploading:
   ```bash
   export FCMR_DUCKDB_MEMORY_LIMIT="2GB"  # or smaller
   ```
   Then restart the app. DuckDB will spill to disk instead of OOM-ing.

2. **Increase available RAM** on the system (if possible).

3. **Split large files** into smaller chunks before uploading.

**Recommended action:** Upgrade to v0.1.30 immediately — this is a critical bug blocking
large-file audits.

---

## "FileNotFoundError on run"

### Symptom
A run fails with:
```
FileNotFoundError: Data file not found at <path/to/parquet>. Please re-upload the CSV file.
```

The error occurs during the run, after the upload was marked ready and the run was started.

### Root Cause
After ingesting a CSV into DuckDB, the intermediate Parquet file is **deleted to save disk
space**. The ingestion pipeline is designed to:
1. Stream CSV → Parquet (temporary intermediate file)
2. Parquet → DuckDB table (durable copy)
3. Delete Parquet (no longer needed)

If step 2 (the DuckDB import) fails for any reason (e.g., DuckDB error, insufficient disk
space), the fallback code tries to recover by reading the Parquet. But the Parquet may
already be deleted, triggering a FileNotFoundError.

This is rare in normal operation. It can occur if:
- The DuckDB connection is interrupted mid-import.
- The disk fills up during import.
- The upload table metadata is corrupted.

### Fix
1. **Re-upload the CSV file.** The data is no longer in the system, so a fresh upload
   will re-ingest it cleanly.
2. **Check disk space.** Ensure the system has at least 1.5× the CSV file size free
   before uploading.
3. **Check DuckDB logs.** If the problem persists, check `data/logs/error.log` for
   DuckDB-level issues.

### Prevention
- Keep disk space > 50% free before large uploads.
- Avoid interrupting the app during ingestion (watch the upload status indicator).

---

## "Desktop: backend did not respond after 90 seconds"

### Symptom
You launch the SanGir Automations desktop app (Windows/macOS/Linux). Electron shows a
modal dialog:
```
Startup Error

Failed to start SanGir Automations:
Backend did not respond after 90 seconds.

Log file: <path/to/backend.log>
```

The app fails to start. Clicking "OK" closes the dialog and the app exits.

### Root Cause (v0.1.29 bug, fixed in v0.1.30)
The DuckDB catalog (`catalog.duckdb`) uses SQLite-style **single-writer locking**. When
a process opens the file for read-write access, it acquires an exclusive lock. If the
process **crashes or exits ungracefully** (e.g., killed by the OS, Electron window force-closed)
the lock is never released.

When you launch the app again:
1. Electron spawns `sangir-backend.exe`.
2. The backend tries to open `catalog.duckdb` for read-write.
3. DuckDB detects the stale lock and **blocks indefinitely** waiting for the lock holder.
4. The backend never responds to HTTP requests.
5. Electron's 90-second timeout fires → startup error.

This is environmental, not a code bug, but v0.1.29 had no defense against it.

### Fix (v0.1.30+)
Upgrade to v0.1.30 or later. The fix includes:
1. **Graceful shutdown:** The backend now closes the DuckDB connection cleanly on exit
   (via `atexit` and signal handlers in `desktop_backend.py`), releasing the lock.
2. **Orphan reaping:** Before spawning a new backend, Electron kills any stale
   `sangir-backend.exe` processes on Windows with `taskkill`, clearing the lock before
   it's even acquired.
3. **Lifespan cleanup:** The FastAPI lifespan now calls `store.close_catalog()` on
   shutdown (in `app/main.py`).

### Manual Recovery (v0.1.29 or v0.1.30+ with a crashed backend)
If you hit this error:

1. **Force-kill any orphaned backend processes:**
   - **Windows:** Open Task Manager → find `sangir-backend.exe` → right-click → End Task.
   - **macOS/Linux:** Open Terminal → run `pkill sangir-backend`.

2. **Delete the stale DuckDB lock file (optional):**
   - On Windows: `%LOCALAPPDATA%\SanGirAutomations\catalog.duckdb-wal` (if present).
   - On macOS: `~/.sangir/catalog.duckdb-wal`.
   - On Linux: `~/.sangir/catalog.duckdb-wal`.

3. **Restart the app.**

The lock should now be cleared and the app will start normally.

---

## "Still loading no output" — downloads or exports stuck

### Symptom
You click a download button (e.g., "Download Missing Data", "Download Wide CSV", "Export
Workpaper"). The page shows a loading overlay that says "Downloading…" or "Preparing…"
but never dismisses. The file never downloads.

### Root Cause
The loading overlay uses a **download-cookie handshake** to know when the file is ready.
It polls the browser's cookies for a `dl_done_<token>` marker. If the download completes
but the cookie is never set (due to a middleware issue or a response that doesn't include
the expected headers), the overlay waits indefinitely.

This can also happen if:
- The backend is slow (e.g., generating a large workpaper) and the 20-second poll timeout
  is too short.
- A network issue causes the download to fail silently.

### Fix
1. **Check browser console** for JavaScript errors:
   - Open Developer Tools (F12).
   - Go to Console tab.
   - Look for errors related to `dl_token` or `dl_done`.

2. **Refresh the page** and try again. Sometimes a stale cookie or session state causes
   the issue.

3. **Check the processing log** for errors during export/download:
   ```
   cat data/logs/processing.log | tail -20
   ```
   Look for `ERROR` lines mentioning workpaper or CSV generation.

4. **Increase the timeout** (temporary workaround):
   - Wait > 20 seconds (the default poll timeout).
   - Manually navigate to the download URL in the address bar (inspect the button's href).

5. **Restart the backend** if the issue persists (dev mode):
   ```bash
   # Stop: Ctrl+C
   # Restart:
   python -m uvicorn app.main:app --reload
   ```

---

## DuckDB memory limits and spill

### What are DuckDB limits?

The `apply_duckdb_limits()` function sets three DuckDB parameters to protect against OOM:
1. **`memory_limit`** — max RAM per operation (e.g., 3–12 GB depending on system RAM).
2. **`threads`** — number of worker threads (e.g., 2–6).
3. **`temp_directory`** — path for disk spill when RAM is exhausted.

These limits are **automatically detected** based on the system's available RAM (hardware
tier: low < 12 GB, mid 12–24 GB, high > 24 GB).

### Why is this important?

Without limits, DuckDB will try to load entire large files into RAM, causing OOM. With
limits, DuckDB gracefully **spills to disk** when it exceeds the memory cap, trading
speed for safety on constrained systems.

### How to override limits

Set environment variables **before** starting the app:

```bash
# Override memory limit (in MB or with suffix GB, TB)
export FCMR_DUCKDB_MEMORY_LIMIT="4GB"

# Override thread count
export FCMR_DUCKDB_THREADS="2"

# Override hardware tier detection
export FCMR_HW_TIER="low"  # or "mid", "high"

# Restart the app
python -m uvicorn app.main:app --reload  # or start the desktop app
```

### Example: Processing a 9M-row file on a 8 GB laptop

1. Detect tier: **low** (< 12 GB RAM) → 3 GB memory limit, 2 threads.
2. Upload the file and run analytics.
3. If you hit OOM: lower the limit further:
   ```bash
   export FCMR_DUCKDB_MEMORY_LIMIT="2GB"
   # Restart and retry
   ```

---

## For Contributors: The DuckDB Limits Rule

**INVARIANT:** Every `duckdb.connect()` that performs analytics **MUST** be immediately
followed by `apply_duckdb_limits(con)`.

This ensures that rules, sampling, and reporting pipelines respect hardware constraints.

### Call sites (reference)
- ✓ `fcmr_core/catalog/store.py:37` — catalog persistence
- ✓ `fcmr_core/ingestion/pipeline.py:130` — CSV ingest (v0.1.30+)
- ✓ `fcmr_core/rules/duplicates.py:87` — duplicate detection
- ✓ `fcmr_core/ingestion/consolidation.py:173` — multi-file merge
- ✓ `fcmr_core/reference/pin_master.py:43` — PIN master load

When adding a new analytics connection, copy the pattern:
```python
with duckdb.connect(...) as con:
    apply_duckdb_limits(con)
    # ... analytics code ...
```

---

## Getting help

If you encounter an issue not covered here:

1. **Check the application logs:**
   ```
   data/logs/app.log           # general logs
   data/logs/processing.log    # run/ingestion logs
   data/logs/error.log         # errors only
   ```

2. **Provide the log snippet** when reporting issues (redact any PII like PAN/Aadhaar hashes).

3. **Desktop app logs** are at:
   - Windows: `%LOCALAPPDATA%\SanGirAutomations\logs\backend.log`
   - macOS: `~/.sangir/logs/backend.log`
   - Linux: `~/.sangir/logs/backend.log`

4. **Report at:** [GitHub Issues](https://github.com/ihbsandeepreddy/FCMR/issues)
