# CLAUDE.md — SanGir Automations (FCMR) — Single Source of Truth

> **This is the one authoritative document for the project.** It captures the full
> infrastructure, UI, and the decisions behind them. All future work — and every
> change suggestion — must be evaluated against, and kept consistent with, this file.
> When code and this document disagree, treat it as a bug in one of them and reconcile
> immediately (update the code or update this doc in the same change).
>
> **Last reconciled with code:** 2026-06-20 (v0.1.30 bugfix + hardening pass).
> Supersedes the old phase-spec `CLAUDE.md` and the marketing-style `README.md`.

---

## 0. How this document is used (operating agreement)

1. **Single source of truth.** This file describes what *is* true in the code today plus
   the *intent* behind it. The old "Phases 0–6" framing has been retired — the product is
   past phasing; it is described here by capability, not by phase.
2. **Change protocol.** When a change is requested, the assistant will:
   - locate **every** layer the change touches (schema YAML, rules, catalog/store, API
     route, template, CSS, config, tests, deployment), make the edits across all of them so
     the change is internally consistent, then
   - **report back exactly what changed** (files + one-line rationale each), and
   - update the relevant section of this document in the same pass.
   See [§22 Change checklist by layer](#22-change-checklist-by-layer).
3. **Decisions are sticky.** [§20 Decision log](#20-decision-log) records *why* things are
   the way they are. Do not silently reverse a logged decision — flag it and confirm first.

---

## 1. Product overview

**SanGir Automations** (internal/repo name **FCMR**) is a **deterministic audit-analytics
web tool** for NBFC loan-portfolio validation. An auditor creates an *engagement*, uploads
operational CSV exports, maps their columns to canonical fields, runs hard-coded validation
rules, and downloads exception reports and an Excel audit workpaper.

Two distinct capabilities live in the app:

| Capability | Input report type | What it does |
|---|---|---|
| **KYC / data-quality analytics** | `customer_master` | Runs the 24-rule deterministic pipeline → wide/long exception CSVs, dashboard charts, ICAI-sampled 4-sheet Excel workpaper. |
| **Multi-file consolidation** | any report type | Multi-file/folder uploads are merged into one source at ingest time, with a guided schema-reconciliation step when layouts differ (§9); the consolidated source is mapped/analyzed/downloaded like any upload. Used heavily for `ead_files` (39 ECL/EAD columns), no rules run there. |

Other report types (`collection_report`, `disbursement_report`, `technical_writeoff`) have
schemas for ingestion/mapping but **no dedicated analytics yet** — they ingest and store, and
the rule pipeline only produces meaningful results for `customer_master`.

### Non-negotiable invariants

1. **No AI/LLM anywhere.** All logic is hard-coded and deterministic. Fuzzy matching uses
   stdlib `difflib.SequenceMatcher` (column mapping) and token-set Jaccard (address). No
   embeddings, no model calls. This is a hard auditability requirement.
2. **Aadhaar protection.** Never persist or display a full Aadhaar. Use a **salted SHA-256
   hash** for dedup/grouping; show masked `XXXXXXXX1234` in any output. Salt comes from
   `FCMR_AADHAAR_HASH_SALT`.
3. **Deterministic reproducibility.** Same input + same seed ⇒ identical output. Sampling
   seed = `SHA256(engagement_id:run_id)`; UCID/group IDs are hash-derived.
4. **Additive schema migrations only.** Catalog changes use `CREATE TABLE IF NOT EXISTS` and
   guarded `ALTER TABLE … ADD COLUMN`. No `DROP COLUMN`/`DROP TABLE`. This protects existing
   data across `git pull` + restart **on local/desktop** (see the Vercel caveat in §1.5).
5. **Memory-aware ingestion.** CSV → Parquet conversion is delegated to DuckDB's streaming
   `read_csv` (never `pd.read_csv` of the whole file). *Caveat:* the per-row rule loops and
   the UCID/address O(n²) passes are **not** streaming — see [§18 scaling notes](#18-known-limitations--scaling-notes).
6. **DuckDB memory limits on every analytics connection.** Every `duckdb.connect()` that
   performs analytics **MUST** be immediately followed by `apply_duckdb_limits(con)`. This
   prevents OOM on large files. See [§11 Configuration](#11-configuration--environment-variables)
   and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for details.
7. **Runs are engagement-scoped.** When creating a run, the active engagement ID **MUST** be
   passed to `store.create_run(upload_id, engagement_id)` so the run is visible in the
   engagement's `/runs` list. Runs without engagement_id are hidden.

### 1.5 Deployment reality (important)

The app detects its deployment environment in `fcmr_core/config.py` via `sys.frozen` (PyInstaller)
and the `VERCEL` env var. Three environments:

| | **Dev (uvicorn)** | **Desktop (Electron+PyInstaller)** | **Vercel serverless** |
|---|---|---|---|
| Data root | `<repo>/data/` | Windows: `%LOCALAPPDATA%/SanGirAutomations`; others: `~/.sangir` | `/tmp/fcmr/` (**ephemeral**) |
| Catalog | `data/catalog.duckdb` | per-user appdata, persistent | `/tmp/fcmr/catalog.duckdb` wiped on cold start |
| Large uploads | streamed to disk | streamed to disk | direct browser→**Vercel Blob** (4.5 MB limit) |
| Session secret | auto-gen → `data/.session_secret` | auto-gen → appdata | **must** set `FCMR_SESSION_SECRET` (else startup raises) |
| DuckDB limits | tier-auto-detected (`apply_duckdb_limits`) | tier-auto-detected | tier-auto-detected |
| Use case | development | real audit work, offline-capable | demos / preview only |

> ⚠️ **Data survival (invariant #4) only holds on dev and desktop.** On Vercel the catalog is
> a throwaway. The desktop build is the primary durable deployment path — it uses per-user
> appdata so no admin rights are needed.

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python ≥ 3.11 (CI runs 3.13) | typing, async, data ecosystem |
| Web framework | FastAPI + Uvicorn | async, built-in OpenAPI, Starlette session middleware |
| Templating | Jinja2 (server-rendered) | no SPA; logic stays in Python |
| Front-end JS | htmx (CDN) + small vanilla scripts | progressive enhancement only (upload progress, file pickers) |
| CSV ingest | DuckDB `read_csv` (streaming) | encoding/delimiter sniffing, `ignore_errors`, large files |
| Working store | **DuckDB tables** inside `catalog.duckdb` | one embedded DB for catalog *and* row data (see §4) |
| In-memory analytics | Polars `DataFrame` | fast per-column ops; rules read it row-wise |
| Cross-row dedup | DuckDB self-joins (`duplicates.py`) | SQL EXISTS for shared-key detection |
| Excel | openpyxl | workpaper + consolidated-data export |
| Charts | hand-rolled SVG (`reporting/charts.py`) | zero chart deps, inline-safe |
| Config | pydantic-settings | env-prefixed `FCMR_*`, `.env` support |
| Auth | PBKDF2-HMAC-SHA256 (100k iters) + signed-cookie sessions | stdlib only |
| Logging | Python `logging` + `RotatingFileHandler` via `logging_setup.py` | 4 dedicated log files, no PII |
| System monitoring | `psutil` + `/api/system/*` JSON endpoints | RAM/CPU/DuckDB state; feeds Settings page |
| Desktop shell | Electron (Node.js) + PyInstaller (.exe/.app) | wraps FastAPI backend; auto-update via GitHub Releases |

Full dependency list: `pyproject.toml` (canonical) and `requirements.txt` (Vercel runtime,
kept in sync with `pyproject.toml`).

---

## 3. Architecture & repository layout

```
FCMR/
├── api/index.py                  Vercel entry — re-exports app.main:app
├── desktop_backend.py            PyInstaller entry — imports app and runs uvicorn directly
├── app/                          FastAPI web layer (thin)
│   ├── main.py                   App factory, lifespan init, middleware, router wiring
│   ├── api/
│   │   ├── auth.py               PBKDF2 login/logout, seed admin/admin123
│   │   ├── engagements.py        Create/list/select engagement ("/" is the selector)
│   │   ├── uploads.py            Upload + column-mapping UI + dashboard ("/dashboard")
│   │   ├── runs.py               Run analytics (background task), charts, workpaper export
│   │   ├── downloads.py          Wide/long CSV download
│   │   ├── settings.py           Settings page (fuzzy threshold + system monitoring)
│   │   ├── system.py             /api/system/info|usage|logs — JSON endpoints (psutil)
│   │   ├── blob_upload.py        Vercel Blob token + register-from-blob (large files)
│   │   └── consolidate.py        Schema-reconciliation screen + consolidated-data downloads
│   └── web/
│       ├── templates/            Jinja2: base, login, engagements, index, upload,
│       │                          upload_detail, column_map, run_detail, settings,
│       │                          reconcile
│       └── static/css/main.css   The entire design system (see §16)
│
├── fcmr_core/                    Business logic (UI-independent, testable)
│   ├── config.py                 Settings (paths, env detection, DuckDB limits, secrets)
│   ├── logging_setup.py          get_logger() → 4 rotating files (app/processing/error/update)
│   ├── backup.py                 create_backup() / restore_backup() → data/backups/
│   ├── catalog/store.py          DuckDB: catalog tables + row-data tables + CRUD + migrations
│   ├── ingestion/pipeline.py     CSV → Parquet (DuckDB streaming), header sniff, rejects
│   ├── ingestion/consolidation.py Multi-file grouping, schema alignment, combined-CSV merge (§9)
│   ├── schemas/                  Column-mapping YAMLs + loader (confidence scoring)
│   │   ├── customer_master.yaml  ~22 canonical KYC fields (analytics target)
│   │   ├── ead_files.yaml        39 canonical ECL/EAD fields (L&T Finance LMS names)
│   │   ├── collection_report.yaml / disbursement_report.yaml / technical_writeoff.yaml
│   │   └── loader.py             SchemaMap, alias index, difflib scoring, threshold
│   ├── rules/                    24 deterministic rules grouped into 4 categories (see §6)
│   │   ├── registry.py           @register, CATEGORIES, run_pipeline(), list_categories(),
│   │   │                          resolve_rule_ids(), _coerce_str_columns()
│   │   ├── ucid.py               Union-find grouping + KYC-consistency flag
│   │   ├── kyc_format.py         PAN/Aadhaar(Verhoeff)/Voter/Passport/DL/Mobile/Email/DOB
│   │   ├── duplicates.py         PAN/Aadhaar/Mobile/Bank/VoterID/Name+DOB/Address dupes
│   │   ├── pincode_address.py    PIN existence, state/district match, completeness
│   │   ├── email.py              Generic-domain email warning
│   │   ├── bank_account.py       Account length (9–18 digits)
│   │   └── beneficiary.py        Stable customer key + group id (tagging, always OK)
│   ├── reporting/
│   │   ├── builder.py            Wide + long exception CSVs
│   │   ├── aggregation.py        Status counts, top exception codes
│   │   ├── charts.py             SVG donut + horizontal bar
│   │   └── workpaper.py          4-sheet Excel (Lead / Detailed / TOC-TOD / Methodology)
│   ├── sampling/
│   │   ├── stratification.py     Severity strata (CRITICAL/HIGH/MEDIUM/LOW)
│   │   ├── icai_table.py         ICAI-ICFR attribute sample-size table (95% conf)
│   │   └── sample.py             Seeded proportional stratified selection
│   └── reference/pin_master.py   India Post PIN master (Parquet, lru_cached)
│
├── electron/                     Electron shell (desktop app)
│   ├── main.js                   Main process: spawn backend, auto-port, 90s timeout, log file
│   ├── preload.js                Context bridge (renderer ↔ main)
│   └── updater.js                Auto-update via electron-updater + GitHub Releases
├── build/
│   ├── sangir-backend.spec       PyInstaller spec — bundles Python + fcmr_core into .exe
│   └── installer.nsh             NSIS installer customisation (Windows)
├── package.json                  Electron + electron-builder (desktop build)
├── electron-builder.yml          Build targets (Windows NSIS, macOS dmg, Linux AppImage)
│
├── tests/                        pytest: kyc_format, duplicates, ingestion, pincode_address,
│                                  categories (run_pipeline filtering), e2e workpaper
├── pyproject.toml                deps, ruff, black, pytest config
├── requirements.txt              Vercel runtime deps (subset — see §18)
├── vercel.json                   builds api/index.py, routes /* → it
├── start.bat                     one-click local: venv → git pull → uvicorn --reload :8000
├── .env.example                  template for local dev vars
├── .env.production.example       template for Vercel/prod vars
└── .github/workflows/ci.yml      ruff + black --check + pytest (py3.13)
      .github/workflows/release.yml  build + publish Electron installers on git tag
```

### Request → data flow (customer_master analytics)

```
Upload CSV ──► (disk 256KB chunks, or Vercel Blob) ──► sniff headers ──► status=mapping_pending
   │
Map columns (auto-suggested via difflib ≥ threshold, or saved profile) ──► confirm
   │
ingest_csv(): DuckDB read_csv → rename to canonical → COPY to Parquet (ZSTD) + _row_num
   │
store_upload_data(): import Parquet into DuckDB table `data_<upload_id>`; DELETE Parquet + raw CSV
   │   (mapping saved as a reusable profile keyed by SHA256(sorted headers))
status=ready
   │
Run ──► background task: get_upload_df() (Polars) → run_pipeline() (24 rules) →
        build_exception_csvs() → data/outputs/<run_id>/{wide,long}.csv → status=completed
   │
Run detail page: donut + bar SVG, summary
   │
Export workpaper ──► ICAI sample size → seeded stratified sample → 4-sheet .xlsx
```

---

## 4. Data model (DuckDB — `catalog.duckdb`)

Defined and migrated in `fcmr_core/catalog/store.py::init_catalog()`. **Two kinds of tables
live in the same DuckDB file:** fixed *catalog* tables, and one *row-data* table per upload.

### Catalog tables

```sql
users(username PK, password_hash, display_name, created_at)
  -- password_hash stored as "salt:pbkdf2hash"; seed admin/admin123 on startup

engagements(engagement_id PK, name, client_name, period_from, period_to,
            status='active', created_by → users, created_at)
  -- one engagement = one audit job; a "default" engagement is auto-created and
  -- used to backfill legacy rows. Active engagement is held in session.

uploads(upload_id PK, report_type, filename, csv_path, sniffed_headers(JSON),
        column_mapping(JSON {raw:canonical}), row_count, parquet_path,
        status, engagement_id → engagements, created_at,
        batch_id, ingested_at,            -- batch_id/ingested_at added via ALTER
        is_consolidated, source_count, source_files_json)  -- consolidation meta (ALTER)
  -- status: mapping_pending → ready → (failed). csv_path may be a local path OR a blob URL.
  -- is_consolidated=1 marks a merged multi-file source; source_files_json lists origin names.

batches(batch_id PK, report_type, engagement_id, status, files_json(JSON),
        consolidated_upload_id, created_at)
  -- one row per multi-file upload awaiting schema reconciliation (§9).
  -- status: reconcile_pending → consolidated | failed. files_json = [{name,path,headers}].

runs(run_id PK, upload_id → uploads, engagement_id, status, started_at, finished_at,
     wide_csv, long_csv, error, workpaper_path)
  -- status: pending → running → completed | failed

mapping_profiles(profile_id PK, report_type, header_signature, mapping_json,
                 engagement_id NULLABLE, created_by, created_at,
                 UNIQUE(report_type, header_signature, engagement_id))
  -- header_signature = SHA256(sorted(raw_headers)); engagement_id NULL = global profile.
  -- On matching future headers → mapping auto-applied (no manual remap).

settings(key PK, value, updated_at)
  -- e.g. fuzzy_match_threshold; read by schema loader, edited via /settings.
```

### Row-data tables (the working store)

- After mapping, each upload's data is imported into a table named
  **`data_<upload_id-with-underscores>`** via `store_upload_data()`, and the intermediate
  Parquet + raw CSV are **deleted**. `get_upload_df()` reads it back as a Polars DataFrame.
- **Implication:** the old "data lives in `data/parquet/<upload_id>/`" model is gone. Parquet
  is now a transient intermediate; the durable copy is a DuckDB table. `outputs/<run_id>/`
  CSVs and workpapers are still written to the filesystem.

---

## 5. Report types & schemas

Schemas are YAML in `fcmr_core/schemas/`, loaded by `loader.py`. Each canonical field has
`aliases` (case-insensitive), `required`, `dtype`. The loader builds an alias→canonical index
and scores unknown headers with `difflib.SequenceMatcher`, suggesting a mapping when the best
score ≥ the configurable `fuzzy_match_threshold` (default **0.6**, editable at `/settings`).

| report_type | Required fields | Purpose | Analytics? |
|---|---|---|---|
| `customer_master` | `customer_id`, `full_name`, `lan` | KYC master; full 24-rule pipeline | ✅ rules |
| `ead_files` | `loan_id` | 39 ECL/EAD columns (DrsPOS, DPDBucketing, EAD, provisions…) | merge/consolidate only |
| `collection_report` | `loan_account_no` | collections | ingest only |
| `disbursement_report` | `loan_account_no`, `disbursement_date` | disbursements | ingest only |
| `technical_writeoff` | `loan_account_no` | write-offs | ingest only |

**To add a report type:** create `schemas/<name>.yaml` (the loader auto-discovers `*.yaml` on
reload) → it appears in the upload dropdown automatically. If it needs analytics, add rules
(§11) that read its canonical fields.

---

## 6. Rules engine

**Mechanism (`rules/registry.py`):**
- A rule is `fn(df: pl.DataFrame) -> pl.DataFrame` registered via `@register(rule_id, description)`.
- `run_pipeline(df, rule_ids=None, on_progress=None)`:
  - First calls `_coerce_str_columns()` (casts numeric-inferred columns — except the
    `_NUMERIC_CANONICALS` allowlist — to `Utf8`, so `.strip()` in rules never hits an `int`).
  - If `rule_ids` is provided, runs only those rules (preserving registry order); `None` = all.
  - Calls `on_progress(completed, total, rule_id)` after each rule (used by Settings UI to
    display progress during selective runs).
- Each rule appends three columns: `_exc_<rule_id>_status` ("OK"|"WARN"|"ERROR"),
  `_exc_<rule_id>_code`, `_exc_<rule_id>_desc`. `reporting/builder.py` collapses these.
- Rules are loaded once on first run via `_ensure_rules_loaded()` (import side effects).

**Rule categories** — the 24 rules are grouped into 4 categories (defined in `CATEGORIES`
in `registry.py`). Users can run a whole category or individual rules from the run UI:

| Category id | Label | Rule ids (count) |
|---|---|---|
| `kyc_format` | KYC & Document Format | pan_format, aadhaar_format, voter_id_format, passport_format, dl_format, mobile_format, email_format, dob_validity, dob_age_range, bank_account_invalid_length, email_company_generic_domain **(11)** |
| `address_pin` | Address & PIN | pincode_exists, state_pin_match, district_pin_match, address_completeness **(4)** |
| `duplicates` | Duplicate Detection | pan_duplicate, aadhaar_duplicate, mobile_duplicate, bank_account_duplicate, name_dob_duplicate, voter_id_duplicate, address_duplicate **(7)** |
| `identity_grouping` | Identity Grouping | ucid, beneficiary_tagging **(2)** |

`list_categories()` returns these enriched with descriptions. `resolve_rule_ids(category_ids, rule_ids)` merges category selection with individual rule selection → a flat list; returns `None` (= run all) when both are empty.

**The 24 registered rules** (count is authoritative — older docs said 27):

| Module | rule_id(s) | Severity of findings |
|---|---|---|
| `ucid.py` | `ucid` (+ emits `ucid`, `ucid_size`) | WARN `UCID_KYC_INCONSISTENT` |
| `kyc_format.py` | `pan_format`, `aadhaar_format`, `voter_id_format`, `passport_format`, `dl_format`, `mobile_format`, `email_format`, `dob_validity`, `dob_age_range` | ERROR/WARN |
| `pincode_address.py` | `pincode_exists`, `state_pin_match`, `district_pin_match`, `address_completeness` | ERROR/WARN |
| `duplicates.py` | `pan_duplicate`, `aadhaar_duplicate`, `mobile_duplicate`, `bank_account_duplicate`, `name_dob_duplicate`, `voter_id_duplicate`, `address_duplicate` | ERROR (WARN for address) |
| `email.py` | `email_company_generic_domain` | WARN |
| `bank_account.py` | `bank_account_invalid_length` | ERROR |
| `beneficiary.py` | `beneficiary_tagging` (emits `fcmr_customer_key`, `fcmr_group_id`) | always OK (tagging) |

**Key rule logic worth knowing:**
- **UCID** = union-find over rows connected by exact PAN / Aadhaar-hash / Voter ID /
  Name+DOB / bank account / fuzzy address (Jaccard ≥ 0.85). Flags KYC inconsistency when a
  group has conflicting PAN/Aadhaar/Voter/email/mobile/state/pincode.
- **Duplicate scoping:** a shared key is **allowed (OK)** only when rows share the same UCID
  **and** have distinct `lan`s (same person, different loans). Otherwise flagged.
- **Aadhaar** validated by Verhoeff checksum; never stored raw (hash for dedup, mask for display).
- **PIN** checks resolve against the bundled India Post master (`reference/pin_master.py`).

**To add a rule:** write `fn(df)->df` in the right module, decorate with `@register`, return
the three `_exc_*` columns, ensure the module is imported in `_ensure_rules_loaded()`, add a
test. If it produces a new exception code, also register its **severity** in
`sampling/stratification.py::_SEVERITY_MAP` and (optionally) a color in `reporting/charts.py`
and a source-doc label in `reporting/workpaper.py`.

---

## 7. Reporting outputs

`reporting/builder.py::build_exception_csvs()` writes, per run, into `data/outputs/<run_id>/`:

- **`<run_id>_wide.csv`** — one row per input record (internal `_exc_*` columns dropped) plus
  `overall_status` (worst of OK<WARN<ERROR), `exception_count`, `exception_codes` (pipe-joined),
  `exception_descriptions` (pipe-joined).
- **`<run_id>_long.csv`** — one row per (record, non-OK exception): `_row_num`, `customer_id`,
  `rule_id`, `status`, `exception_code`, `exception_description`.

`reporting/aggregation.py` derives status counts and top-N exception-code frequencies from the
wide CSV. `reporting/charts.py` renders an inline SVG donut (status) and horizontal bar (top
codes) — pure string-built SVG, no libraries.

---

## 8. Sampling & Excel workpaper

For `customer_master` runs, **Export Workpaper** produces a 4-sheet `.xlsx`:

1. **Lead Sheet** — engagement info, OK/WARN/ERROR breakdown, top exception codes with mapped
   source document + compliance point.
2. **Detailed Exceptions** — `customer_id`, status, count, codes, descriptions.
3. **TOC/TOD** — the sampled rows with blank `Tested_By / Date / Sign_Off` columns and a
   `Selection_Reason` per sample.
4. **Methodology** — sampling approach, strata weights, confidence/precision, standards (ICAI,
   ISA 530, RBI KYC, NFRA).

**Sampling pipeline:** `sampling/stratification.py` buckets rows into CRITICAL/HIGH/MEDIUM/LOW
by their worst exception code → `sampling/icai_table.py` gives the sample size from the
ICAI-ICFR 95%-confidence attribute table (by population band × expected deviation) →
`sampling/sample.py` seeds `random` with `SHA256(engagement_id:run_id)` and does proportional
stratified selection. **Reproducible by construction.**

To wire a new exception code into sampling, add it to `_SEVERITY_MAP` (else it defaults to LOW).

---

## 9. Ingest-time consolidation & schema reconciliation

**Multi-file / folder uploads are consolidated into ONE source at ingest time** (default on;
a per-upload "Consolidate into a single source" toggle on the upload form lets the user opt
out and keep one upload per file). This replaces both the old post-upload "Data Consolidation"
tab and the EAD-specific merge flow — every report type now consolidates through one generic
path. Logic lives in `fcmr_core/ingestion/consolidation.py`; the UI/route layer is
`app/api/uploads.py::do_upload` + `app/api/consolidate.py` (reconcile + downloads).

**Flow:**
1. `do_upload` collects all CSVs (folder, multi-file, or zip-extracted). One file or
   consolidation-off → legacy per-file uploads (unchanged).
2. Multi-file + consolidate-on → raws staged to `uploads/_batch_<batch_id>/`, headers sniffed,
   and `group_files_by_signature()` groups files by `SHA256(sorted(headers))`.
3. **One layout** → `build_combined_csv()` merges immediately (identity alignment), creating
   ONE consolidated upload → redirect to its `map-columns`.
4. **>1 layout** (schema mismatch) → a `batches` row (`reconcile_pending`) is created and the
   user is sent to **`GET /consolidate/reconcile/{batch_id}`** — a guided-alignment grid (rows =
   unified columns = union of all headers; one editable name column + one `<select>` per file
   layout, pre-filled by `suggest_alignment()` = exact then `difflib` fuzzy ≥ threshold). On
   submit, the chosen alignment drives `build_combined_csv()` → one consolidated upload.

**`build_combined_csv()`** (DuckDB, one pass): per file `SELECT "<raw>" AS "<unified>" | NULL …,
'<filename>' AS _source_file FROM read_csv(..., all_varchar=true)` joined by `UNION ALL BY NAME`,
`COPY … TO` the combined CSV. `all_varchar` avoids cross-file type clashes; types are re-inferred
by the normal `ingest_csv` afterward. The combined CSV is then fed into the **unchanged**
single-file `map-columns → ingest_csv → store_upload_data` pipeline, so the consolidated batch
becomes one ordinary `data_<id>` upload (with a surviving `_source_file` column) that analytics,
runs and downloads see with no special-casing.

The upload-detail page shows a **"Consolidated · N files"** badge, a source-file strip, and
**Download CSV / Download Excel** of the merged data (`GET /dashboard/uploads/{id}/download/{csv,excel}`,
2-sheet Excel via `_df_to_excel`). Deterministic throughout (stdlib `difflib` only, invariant #1).

---

## 10. Authentication, sessions & authorization

- **Single admin model.** `admin` / `admin123` seeded on startup (`auth._ensure_admin`).
  Password is PBKDF2-HMAC-SHA256, 100k iterations, stored as `salt:hash`.
  ⚠️ **There is no change-password endpoint yet** despite the "change on first login" notice —
  see §18.
- **Sessions** via Starlette `SessionMiddleware` (signed cookies). `LoginRequiredMiddleware`
  gates everything except `/login`, `/static`, `/api/blob-noop`, redirecting to `/login`.
- Session holds `username`, `display_name`, and the active `engagement_id`/`engagement_name`.
- No role-based access control; not multi-tenant.

---

## 11. Configuration & environment variables

All env vars are prefixed `FCMR_` (pydantic-settings), `.env` supported. Defined in
`fcmr_core/config.py`.

| Var | Default | Notes |
|---|---|---|
| `FCMR_AADHAAR_HASH_SALT` | placeholder | **Set in prod.** Salt for Aadhaar hashing. |
| `FCMR_SESSION_SECRET` | auto (local) | **Required on Vercel** (else startup error); local auto-saves to `data/.session_secret`. |
| `FCMR_FUZZY_MATCH_THRESHOLD` | `0.6` | Also editable live at `/settings` (stored in `settings` table, overrides default). |
| `FCMR_INGEST_CHUNK_ROWS` | `100000` | streaming chunk hint |
| `FCMR_MAX_UPLOAD_BYTES` | `2 GB` | per-file hard limit |
| `FCMR_HW_TIER` | auto-detect | Override hardware tier: `low` (<12 GB RAM) / `mid` (12–24 GB) / `high` (>24 GB). Controls DuckDB memory/thread limits. |
| `FCMR_DUCKDB_MEMORY_LIMIT` | tier-derived | e.g. `"6GB"`. Override if auto-detect gives wrong limit. |
| `FCMR_DUCKDB_THREADS` | tier-derived | Override DuckDB thread count. |
| `FCMR_BACKEND_PORT` | `8000` | Port for uvicorn; Electron sets this to `8765` by default. |
| `BLOB_READ_WRITE_TOKEN` | — | Vercel Blob (not `FCMR_`-prefixed). Enables large-file path. |
| `VERCEL` | set by Vercel | switches data root to `/tmp/fcmr`. |

**Hardware-tier DuckDB limits** (`apply_duckdb_limits(con)` in `config.py`): call this
immediately after opening any DuckDB connection that runs analytics. Sets `memory_limit`,
`threads`, and `temp_directory` (for disk spill at `data/duckdb_spill/`). Tier defaults:
- `low` (<12 GB RAM): 3 GB DuckDB memory, 2 threads
- `mid` (12–24 GB): 6 GB, 4 threads
- `high` (>24 GB): 12 GB, 6 threads

---

## 12. Testing & CI

- **Tests present:** `tests/test_kyc_format.py`, `test_duplicates.py`, `test_ingestion.py`,
  `test_pincode_address.py`, `test_categories.py` (rule filtering + progress callback),
  `test_e2e_workpaper.py` (end-to-end synthetic workpaper; marked `perf`, skip in CI),
  `test_imports.py` (smoke-import all modules), plus `tests/generate_synthetic.py` (fixtures).
  (No `test_ucid` / `test_sampling` yet — still a coverage gap.)
- `pytest` config in `pyproject.toml`; `perf` marker = slow, opt-in only.
- **CI** (`.github/workflows/ci.yml`, Python 3.13): `ruff check .` → `black --check .` →
  `pytest -m "not perf" -v`. Keep ruff/black-clean (line length 100) or CI fails.
- **Release CI** (`.github/workflows/release.yml`): triggered on git tag `v*.*.*`; builds
  PyInstaller `.exe` + Electron NSIS installer; publishes to GitHub Releases for auto-update.

---

## 13. Commands

```bash
# ── Local dev ──────────────────────────────────────────────────────────────
start.bat                                            # Windows one-click: venv → git pull → :8000

python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload                        # http://localhost:8000  (admin/admin123)

ruff check . --fix && black .                        # lint + format
pytest -m "not perf" -v                              # tests (skip slow e2e)
pytest -m perf -v                                    # include e2e workpaper test

# ── Desktop (Electron + PyInstaller) ───────────────────────────────────────
pip install pyinstaller
pyinstaller build/sangir-backend.spec                # builds dist/desktop_backend.exe

npm install                                          # Electron deps (package.json)
npm run electron:dev                                 # launch Electron against dev uvicorn
npm run build:win                                    # NSIS installer (Windows)
npm run build:mac                                    # DMG (macOS)
npm run build:linux                                  # AppImage

# ── Publish ────────────────────────────────────────────────────────────────
git push origin main                                 # fork
git push upstream main                               # upstream (admin access)
git tag v0.1.X && git push upstream --tags           # triggers release CI → GitHub Releases
```

Remotes: `origin` = `GirishMGK/FCMR` (fork), `upstream` = `ihbsandeepreddy/FCMR` (admin).

---

## 14. Logging

`fcmr_core/logging_setup.py` — call `get_logger(name)` to get a `RotatingFileHandler`-backed
logger. Handlers are attached once per name (idempotent on re-import). All logs go to
`{data_dir}/logs/` (created by `ensure_dirs()`).

| Logger name contains | File | Max size | Backups |
|---|---|---|---|
| `processing` or `run` | `processing.log` | 10 MB | 5 |
| `error` | `error.log` | 10 MB | 5 |
| `update` | `update.log` | 5 MB | 3 |
| anything else | `app.log` | 10 MB | 5 |

**PII rule: never log PAN, Aadhaar, names, account numbers, or any customer field.**
Log job IDs, row counts, file names, status transitions — not record content.
A `console_handler` (INFO) is also attached for dev visibility.

Recent log lines are surfaced in the Settings page via `GET /api/system/logs?lines=100`.

---

## 15. System monitoring

`app/api/system.py` — three JSON endpoints, all require login, mounted at `/api`:

| Endpoint | Returns |
|---|---|
| `GET /api/system/info` | hardware tier, total RAM, CPU count/freq, DuckDB limits, key paths |
| `GET /api/system/usage` | live RAM used/available/%, CPU %, DuckDB spill dir size (MB) |
| `GET /api/system/logs` | last N lines of `processing.log` (default 100) |

These feed the **Settings page** (live resource meters + log viewer). The page also shows
the active DuckDB memory limit and threads so auditors can see the resource profile.

---

## 17. Backup & restore

`fcmr_core/backup.py` — programmatic backup/restore of the catalog and outputs:

- `create_backup()` → zips `catalog.duckdb` + `data/.session_secret` + `data/outputs/**`
  into `data/backups/SAND_Backup_<YYYYMMDD_HHMMSS>.zip` (ZIP_DEFLATED). Returns the `Path`.
- `restore_backup(path)` → extracts zip into `data_dir`, overwriting existing catalog.
  **Destructive** — caller must confirm. No UI hook yet; callable from a management script.

Backups are not triggered automatically; they are meant to be called before risky operations
(schema migrations, bulk re-runs) or on a scheduled basis by the operator.

---

## 16. UI & design system

Server-rendered Jinja2 with one global stylesheet: `app/web/static/css/main.css`. The shell
is `templates/base.html`: a fixed **left sidebar** (logo + vertical nav + logout) and a
**topbar** (page title + per-page actions) wrapping scrollable `.page-content`. This warm
theme is the reference design for the user's other tools.

**Theme — "warm beige + terracotta"** (all colors are CSS custom properties in `:root`,
mostly `oklch`):
- Surfaces: `--bg` beige canvas, `--sidebar-bg`, white `--surface` cards, `--border`.
- Accent: terracotta `--accent` / `--accent-h` / `--accent-light` / `--nav-active-bg`.
- Status: `--ok-* / --warn-* / --err-* / --blue-*` (green/amber/red/blue pairs).
- Radius `8px`, soft `--shadow`.

**Typography** (Google Fonts, loaded in `base.html`):
- **DM Sans** — body/UI. **Lora** (serif) — headings, card titles, stat values.
- **IBM Plex Mono** — numbers, codes, IDs, timestamps (`.mono`).

**Component vocabulary (reuse these classes, don't invent new ones):**
- Layout: `.sidebar`, `.nav-item`(`.active`), `.main-area`, `.topbar`, `.page-content`.
- Content: `.card` (`.card-title`/`.card-sub`/`.card-error`), `.stat-row`/`.stat-card`
  (`.stat-ok`/`.stat-warn`), `.page-header`.
- Controls: `.btn` (`.btn-primary`/`.btn-ghost`/`.btn-run`/`.btn-dl`/`.btn-sm`),
  `.form-group`, `.file-drop`, `.col-select`.
- Data: `.data-table`, `.badge` (status `.badge-ready/-running/-completed/-failed/-OK/-WARN/
  -ERROR`, plus `.badge-type` and category badges), `.mono`, `.exc-bar-*`.
- States: `.empty-state`, `.notice` (`.notice-warn`/`.notice-err`), `.spinner`.

**UI conventions:**
- Report-type labels: render `ead_files` as **"EAD Files"**, otherwise `title()` the
  underscored name (see `index.html`/`upload.html`).
- Sidebar nav highlights via `request.url.path` checks; keep new pages consistent.
- Brand string is **"SanGir Automations"** (logo at `/static/img/sangir-logo.png`); the repo
  name "FCMR" is internal only. The sidebar shows the logo **only** — the textual
  "SanGir Automations" label below it was removed (the badge is self-branding). The logo is a
  **transparent PNG** (background chroma-keyed out, original preserved at
  `sangir-logo-original.png`) so it floats on the beige `--sidebar-bg` with no boxed divider.
  Re-cut deterministically via numpy RGB-distance keying if the source art changes (invariant #1).
- Upload UX: client picks file → if > 4 MB and Blob configured, browser uploads to Vercel Blob
  and registers the URL; else standard XHR with a progress bar.

**When adding UI:** extend `base.html`, fill `page_title`/`topbar_actions`/`content` blocks,
reuse existing classes and CSS variables (no hard-coded hex, no new fonts), and keep pages
server-rendered.

---

## 18. Known limitations & scaling notes

- **O(n²) hot spot: `ucid.py`** — pairwise `_should_connect` loop. The "5M-row" claim in
  the old spec is **not realistic** for UCID. Real ceiling is ~tens of thousands of
  `customer_master` rows. Future fix: blocking/keying before pairwise.
- **`address_duplicate` is now O(n × avg_tokens)** (fixed in v0.1.23): builds an inverted
  token index, filters candidate pairs sharing ≥3 tokens, skips buckets > 500 rows, then
  confirms only candidates with Jaccard ≥ 0.85. No longer a scaling concern for typical files.
- **Row-wise Python loops** in most other rules (not vectorized Polars) — correct but not fast.
- **Vercel data is ephemeral** (`/tmp`) — not a system of record (see §1.5).
- **`requirements.txt` is kept in sync** with `pyproject.toml` (v0.1.30+).
- **No change-password / user management** despite the first-login notice; single hard-coded
  `admin`.
- **Analytics is customer_master-only**; other report types ingest but have no rules.
- **Test coverage gaps**: no UCID or sampling tests.
- **Consolidation alignment grid is add/remove-free**: the reconcile UI lets you rename a
  unified column and repoint each layout's source header, but not add or delete unified-column
  rows. Auto-suggest may leave an all-NULL unified column when two files use different names
  for the same field and the fuzzy match wins (harmless — drop it at the map-columns step).

---

## 20. Decision log

| Decision | Rationale | Don't reverse without confirming |
|---|---|---|
| **No LLM/AI; deterministic only** | Audit defensibility & reproducibility | Core product promise |
| **Store row data in DuckDB tables, delete Parquet/CSV after ingest** | Single durable store; survives restart locally; simpler than managing parquet dirs | Changing this touches `store.py`, `uploads.py`, `runs.py`, `consolidate.py` |
| **Consolidate multi-file uploads at ingest time, by default** | One mapped/analyzed source instead of N separately-mapped files; matches how auditors think about a batch | Toggle exists to opt out; replaces the old post-hoc tab + EAD flow |
| **Consolidation builds ONE combined CSV, then reuses the single-file ingest path** | Max reuse — analytics/runs/downloads see a normal upload; zero changes to ingest/rules | Don't fork a parallel ingest path for consolidated data |
| **Hardware-tier DuckDB limits (`apply_duckdb_limits`)** | Prevents OOM on budget laptops; auto-detected, override via env | Always call `apply_duckdb_limits(con)` on every analytics DuckDB connection |
| **Electron + PyInstaller desktop; data in per-user appdata** | No admin rights required; data survives app reinstalls; offline-capable | Desktop is the primary durable deployment (not Vercel) |
| **`address_duplicate` uses inverted token index (not O(n²) loop)** | Scales to real-world file sizes; keeps audit run times reasonable | Do not revert to nested loop |
| **Additive-only catalog migrations** | `git pull` must never destroy local audit data | Hard rule |
| **Aadhaar: salted SHA-256 + masked display** | Legal/privacy; dedup without exposure | Hard rule |
| **Seeded stratified sampling (`SHA256(eng:run)`)** | Reproducible, defensible sample | Hard rule |
| **Column mapping = difflib, threshold-gated, profile-cached** | Deterministic, learns per header signature | — |
| **Vercel = ephemeral demo only** | 4.5 MB body limit + no persistent disk | Don't market Vercel as durable |
| **Warm beige + terracotta, DM Sans/Lora/IBM Plex Mono, sidebar+topbar shell** | House style; reference UI for sibling tools | Keep consistent across tools |
| **htmx + server-rendered Jinja2, no SPA** | Keep logic in Python, low complexity | — |
| **Brand "SanGir Automations"; "FCMR" internal** | Product identity | — |
| **Runs are engagement-scoped** (v0.1.30) | Only runs with a stored `engagement_id` appear in the `/runs` list; prevents orphaned runs | Always pass `engagement_id` to `create_run()` from the session |
| **Selected categories are persisted** (v0.1.30) | Run-detail labels which categories were chosen; supports selective re-runs | Always call `update_run(selected_rules=...)` when mode != "all" |
| **DuckDB memory limits on every analytics connection** (v0.1.30) | Prevents OOM on large files; enables graceful disk spill on constrained systems | Apply limits immediately after `duckdb.connect()` in all analytics paths |
| **Catalog connection closed on shutdown** (v0.1.30) | Graceful release of DuckDB single-writer lock; allows Electron to reap orphaned processes | Call `store.close_catalog()` in lifespan shutdown + signal handlers on desktop |
| **Catalog connect is bounded/fails-fast** (v0.1.31) | `duckdb.connect()` is wrapped with a ~15s timeout + retry; fails fast with a logged error instead of hanging indefinitely when the catalog is locked | Always log lock errors clearly; desktop backend self-heals via orphan reap + retry on lock |

---

## 22. Change checklist by layer

When a change request comes in, walk this list and touch every box that applies, then report
what changed:

- [ ] **Schema** (`fcmr_core/schemas/*.yaml`) — new/renamed canonical fields, aliases, required.
- [ ] **Rules** (`fcmr_core/rules/*`) — new rule + `@register` + import in `_ensure_rules_loaded`;
      new numeric field? update `_NUMERIC_CANONICALS`; add to the right `CATEGORIES` entry.
- [ ] **Severity/colors** — `sampling/stratification.py::_SEVERITY_MAP`, `reporting/charts.py`,
      `reporting/workpaper.py` source-doc map.
- [ ] **Catalog** (`catalog/store.py`) — new column? guarded `ALTER TABLE … ADD COLUMN` (never
      drop); add CRUD helpers.
- [ ] **API** (`app/api/*`) — route + session/engagement scoping + login gating; new system
      metric? add to `system.py`.
- [ ] **Templates** (`app/web/templates/*`) — extend `base.html`, reuse blocks.
- [ ] **CSS** (`static/css/main.css`) — reuse variables/classes; no new hex/fonts.
- [ ] **Config** (`config.py`) — new `FCMR_*` setting + default; surface at `/settings` if
      live-tunable. New DuckDB connection? call `apply_duckdb_limits(con)`.
- [ ] **Logging** — use `get_logger(name)` from `logging_setup.py`; log job IDs / counts / status,
      **never PII**.
- [ ] **Deps** — update **both** `pyproject.toml` and `requirements.txt`.
- [ ] **Tests** (`tests/`) — add/extend; keep ruff + black clean; mark slow tests `@pytest.mark.perf`.
- [ ] **Desktop** — if adding a new data directory, add it to `ensure_dirs()` in `config.py`.
- [ ] **This doc** — update the affected section(s) and, if a principle changed, §20.

---

## 23. Glossary

- **Engagement** — one audit job; scopes uploads/runs; selected into the session.
- **Upload** — one ingested CSV (rows live in a `data_<id>` DuckDB table).
- **Run** — one execution of the rule pipeline over an upload → wide/long CSVs.
- **UCID** — Unique Customer Identifier; union-find group across matching identifiers.
- **LAN** — Loan Account Number; distinguishes legitimate same-person-multiple-loan rows.
- **Wide / Long CSV** — per-record vs per-exception output shapes.
- **EAD** — Exposure At Default (ECL/Ind AS 109 context); `ead_files` is the consolidation flow.
- **Workpaper** — the 4-sheet Excel audit deliverable with the sampled, sign-off-ready rows.
```
