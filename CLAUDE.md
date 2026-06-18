# CLAUDE.md — SanGir Automations Specification

**Status:** Complete implementation of Phases 0–6 (login, engagements, column mapping, UCID/duplicates, charts, Excel workpaper). This document is the **canonical forward-looking specification** for all future development.

---

## Product Overview

**SanGir Automations** is a **production-grade, deterministic audit analytics tool** for NBFC loan portfolio validation. It ingests large operational CSV exports (customer master, LMS, collection, disbursement data), streams them to Parquet, runs 27 hard-coded validation rules across KYC, duplicates, PIN, and address checks, and produces:
- **Wide exception CSV** (one row per customer)
- **Long exception CSV** (one row per exception, for drill-down)
- **Dashboard charts** (SVG donut + bar)
- **4-sheet Excel workpaper** with deterministic audit sampling

### Non-Negotiable Invariants

1. **No AI/LLM anywhere** — All logic hard-coded, deterministic, unit-tested. Fuzzy matching uses stdlib `difflib.SequenceMatcher`; no embeddings, no models, no API calls.
2. **Memory-bounded streaming** — 5M+ row CSVs process on ~15 GB laptop. Polars `scan_csv` (lazy), DuckDB for cross-row work. Never materialize full CSV.
3. **Aadhaar protection** — Never persist full Aadhaar. Store salted SHA256 hash; display `XXXXXXXX1234` masked form in all outputs (UI, CSV, Excel).
4. **Data-survival invariant** — All schema changes **additive only**. No `DROP COLUMN`, no `DROP TABLE`, no destructive migrations. `CREATE TABLE IF NOT EXISTS`, guarded `ALTER TABLE ... ADD COLUMN`. Ensures `git pull` never deletes user data.
5. **Deterministic reproducibility** — Same input + same seed = same output, always. Seeded random sampling, hash-based mapping profiles, fixed ICAI tables. Auditable and defensible.

---

## Tech Stack & Why

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.13 | Type hints, async support, scientific ecosystem |
| CSV ingest | Polars (lazy `scan_csv`) | Streaming, no full load, faster than Pandas |
| Cross-row work | DuckDB | SQL joins for duplicates, PIN-master validation |
| Working format | Parquet | Columnar, compressed, one-time conversion from CSV |
| Backend | FastAPI + Uvicorn | Async, fast, OpenAPI docs, Session middleware built-in |
| Templates | Jinja2 | Server-rendered (no SPA), decoupled from business logic |
| Catalog | DuckDB | Embedded SQL, persistent, no external DB needed |
| Deployment | Local/Desktop | Git pull + pip install; persistent `data/` directory survives restarts |

**Why not:** Pandas (OOM at 5M rows), Kubernetes (overkill), Vercel (4.5 MB body limit, no persistent disk), LLM matching (non-deterministic, non-auditable).

---

## Feature Summary (Phases 0–6)

| Phase | Feature | Status | Key Files |
|-------|---------|--------|-----------|
| **0** | Rebrand to SanGir Automations | ✅ | `base.html`, `main.py`, logo |
| **1** | Login (PBKDF2) + Engagements workspace | ✅ | `auth.py`, `engagements.py`, session middleware |
| **2** | Folder/file/ZIP ingestion + batch ID + ingested_at | ✅ | `uploads.py`, `upload.html` |
| **3** | Column mapping with % confidence scoring + saved profiles | ✅ | `loader.py`, `uploads.py`, `column_map.html` |
| **4** | UCID (union-find) + enhanced duplicates (LAN-scoped) + 6 new checks | ✅ | `ucid.py`, `duplicates.py`, `email.py`, `bank_account.py`, `kyc_format.py` |
| **5** | Dashboard SVG charts (donut + bar) + export | ✅ | `charts.py`, `aggregation.py`, `run_detail.html` |
| **6** | 4-sheet Excel workpaper + ICAI-ICFR sampling | ✅ | `sampling/`, `workpaper.py`, `/export/workpaper` route |

---

## Architecture

```
SanGir Automations (Local Desktop App)
│
├── app/                              FastAPI web UI (thin layer)
│   ├── main.py                       Router wiring, middleware stack
│   ├── api/
│   │   ├── auth.py                  PBKDF2 login, seed admin/admin123
│   │   ├── engagements.py           Create/list engagements, set active
│   │   ├── uploads.py               Folder/file ingest, column mapping, profiles
│   │   ├── runs.py                  Execute analytics, charts, workpaper export
│   │   └── downloads.py             Download CSV, Excel
│   └── web/
│       ├── templates/               Jinja2 (base, login, engagements, upload, column_map, run_detail, etc.)
│       └── static/                  CSS, logo, favicon
│
├── fcmr_core/                        Business logic (reusable, testable, no UI dependency)
│   ├── config.py                    Pydantic settings (DATA_DIR, AADHAAR_HASH_SALT, etc.)
│   ├── catalog/store.py             DuckDB catalog CRUD (users, engagements, uploads, runs, mapping_profiles)
│   │
│   ├── schemas/                     Column-mapping YAMLs + loader with confidence scoring
│   │   ├── customer_master.yaml     ~24 canonical fields (customer_id, pan, aadhaar, lan, coapplicant_mobile, etc.)
│   │   └── loader.py                SchemaMap class, score_header_match(), map_headers_with_scores()
│   │
│   ├── ingestion/pipeline.py        Streaming CSV → Parquet conversion, structural validation
│   │
│   ├── rules/                       27 deterministic rules (registered via @register decorator)
│   │   ├── registry.py              Rule pipeline runner (run_pipeline())
│   │   ├── kyc_format.py            PAN format, Aadhaar Verhoeff, Voter ID, Passport, DL, Mobile, Email, DOB, Age range
│   │   ├── pincode_address.py       PIN existence, state/district match, completeness
│   │   ├── duplicates.py            PAN, Aadhaar, Mobile, Bank, Voter ID, Address, Name+DOB (LAN-scoped)
│   │   ├── ucid.py                  Union-find grouping, KYC consistency flagging
│   │   ├── email.py                 Company email generic domain detection
│   │   ├── bank_account.py          Bank account length validation (9-18 digits)
│   │   └── beneficiary.py           Stable ID + group keys
│   │
│   ├── reporting/                   Output builders
│   │   ├── builder.py               Wide CSV + Long CSV generation
│   │   ├── aggregation.py           Status/exception-code counts from wide CSV
│   │   ├── charts.py                SVG donut (status) + bar (exception codes)
│   │   └── workpaper.py             4-sheet Excel (Lead, Exceptions, TOC/TOD, Methodology)
│   │
│   ├── sampling/                    Audit sampling (deterministic, reproducible)
│   │   ├── stratification.py        Group by exception severity (CRITICAL/HIGH/MEDIUM/LOW)
│   │   ├── icai_table.py            ICAI-ICFR attribute table lookup (95% confidence)
│   │   └── sample.py                Seeded stratified random selection
│   │
│   └── reference/pin_master.py      Bundled India Post PIN master lookup
│
├── data/                            (gitignored, persistent across restarts)
│   ├── uploads/                     Raw CSV files by upload_id
│   ├── parquet/                     Ingested Parquet by upload_id
│   ├── outputs/                     Exception CSVs + Excel workpapers by run_id
│   └── catalog.duckdb               Persistent store (users, engagements, uploads, runs, profiles)
│
├── pyproject.toml                   Dependencies (openpyxl, polars, duckdb, fastapi, etc.)
└── CLAUDE.md                        This file (canonical specification)
```

---

## Data Model

### Catalog (DuckDB, persistent at `data/catalog.duckdb`)

```sql
users(username, password_hash, display_name, created_at)
  → Single admin for desktop; seed admin/admin123 on startup

engagements(engagement_id, name, client_name, period_from, period_to, status, created_by, created_at)
  → One engagement = one audit job; scopes uploads/runs
  → Users select active engagement → uploads/runs filtered by engagement_id in session

uploads(upload_id, report_type, filename, csv_path, sniffed_headers, column_mapping,
        row_count, parquet_path, status, batch_id, ingested_at, engagement_id, created_at)
  → status: mapping_pending → ready → (used in runs)
  → batch_id: Shared by files in same upload session (folder/multi-file)
  → ingested_at: ISO timestamp after successful Parquet conversion

runs(run_id, upload_id, engagement_id, status, started_at, finished_at,
     wide_csv, long_csv, workpaper_path, error)
  → status: pending → running → completed | failed
  → wide_csv, long_csv, workpaper_path: Paths to output files

mapping_profiles(profile_id, report_type, header_signature, mapping_json, engagement_id, created_by, created_at)
  → header_signature: SHA256(sorted(raw_headers))
  → On matching future headers: auto-apply profile, no manual re-map
  → engagement_id nullable: NULL = global profile, else engagement-scoped
```

### Output CSVs (per run, in `data/outputs/{run_id}/`)

**Wide CSV:**
```
customer_id  full_name  pan  overall_status  exception_count  exception_codes  exception_descriptions
C001         John Doe  XXXXX...  ERROR       2               PAN_DUP|EMAIL_DOM  PAN shared with C005|Email is gmail.com
```

**Long CSV:**
```
customer_id  exception_code  exception_description
C001         PAN_DUP         PAN shared with C005
C001         EMAIL_DOM       Email is gmail.com
```

### Excel Workpaper (4 sheets, in `data/outputs/{run_id}/`)

| Sheet | Purpose | Content |
|-------|---------|---------|
| **Lead Sheet** | Executive summary | Engagement info, status breakdown, top 10 exception codes with source docs |
| **Detailed Exceptions** | Full record data | All columns from wide CSV + exception columns |
| **TOC/TOD** | Test of Controls / Test of Details | Sampled records with blank tester/date/sign-off columns; selection_reason per sample |
| **Methodology** | Sampling approach | ICAI/ISA/RBI/NFRA standards, fraud-risk weights, reproducibility guarantee, confidence/precision stats |

---

## Core Workflows

### Workflow A: Create Engagement → Upload → Map → Run → Export

```
1. User visits "/" (login required)
2. Select or create engagement (name, client, period)
   → Stored in catalog.engagements, session["engagement_id"] = engagement_id
3. Click "New Upload" → POST to /dashboard/upload (folder + file inputs)
   → Generate batch_id, sniff CSV headers for each file
   → Create N upload rows (one per CSV), all with batch_id + engagement_id
   → Redirect to dashboard (shows uploads by batch/status)
4. Click "Map Columns" on upload
   → Compute header_signature = SHA256(sorted(sniffed_headers))
   → Check mapping_profiles table for match
   - If hit: auto-apply profile, show "Profile applied (UUID)"
   - If miss: display auto-suggestions with % confidence (difflib.SequenceMatcher)
5. User confirms mapping (or adjusts)
   → POST to /uploads/{id}/map-columns
   → Stream CSV → Parquet, extract rows, store parquet_path + row_count
   → Save mapping_profile with header_signature + mapping_json
   → Set upload status = "ready"
6. Click "Run Analytics" on ready upload
   → Create run (status=pending), redirect to /runs/{run_id}
   → Background task: Load Parquet → run 27-rule pipeline → build wide/long CSVs
   → Update run status = completed + store CSV paths
7. View run detail page
   → Display donut chart (status breakdown) + bar chart (top 10 exception codes)
   → "Print / PDF" button (browser print-to-PDF)
8. Download options:
   - "Download Workpaper (.xlsx)" → POST /runs/{id}/export/workpaper
     - Stratify exceptions by severity
     - Lookup ICAI-ICFR table → sample size
     - Seeded selection (seed = SHA256(engagement_id + run_id))
     - Generate 4-sheet Excel with sampled rows
   - "Download Wide CSV" → /runs/{id}/download/wide
   - "Download Long CSV" → /runs/{id}/download/long
```

### Workflow B: Deterministic Sampling for Workpaper

```
1. Read wide CSV → parse overall_status + exception_codes columns
2. Stratify into 5 groups:
   - CRITICAL: UCID_KYC_INCONSISTENT, PAN_DUP, AADHAAR_DUP (identity fraud)
   - HIGH: VOTER_DUP, ADDRESS_DUP, BANK_DUP, NAME_DOB_DUP
   - MEDIUM: EMAIL_COMPANY_DOM, DOB_AGE_RANGE, BANK_ACCT_LEN
   - LOW: PIN_MISMATCH, DISTRICT_PIN_MISMATCH, ADDRESS_INCOMPLETE
   - OK: No exceptions
3. Lookup ICAI-ICFR table with:
   - population = total row count
   - exception_count = rows with status != "OK"
   - confidence = 95%, tolerable_deviation = 5%
   → Returns sample size n (e.g., 200 for 50K population)
4. Seeded random selection:
   - Seed = SHA256(engagement_id + run_id) → int (reproducible)
   - Set random.seed(seed)
   - For each stratum: sample proportionally
     sample_size_per_stratum = n * (stratum_size / total_exceptions)
   - random.sample(stratum_indices, sample_size_per_stratum)
5. Tag each sample:
   - row_index, exception_codes, selection_reason ("CRITICAL: PAN_DUP"), criticality
6. Excel TOC/TOD sheet:
   - Row per sample
   - Columns: Sample# | Row_Index | Criticality | Selection_Reason | Tested_By | Date | Sign_Off | Notes
   - Blank sign-off columns for auditors to fill

Same engagement_id + run_id always produces identical sample (reproducible).
```

---

## Rule Modules (27 Rules)

### KYC Format (`kyc_format.py`)
- `pan_format` — AAAAA9999A + entity char
- `aadhaar_format` — 12 digits + Verhoeff checksum
- `voter_id_format` — EPIC (AAA9999999)
- `passport_format` — A-PR-WY + 7 digits
- `dl_format` — State code + RTO + year + sequence
- `mobile_format` — 10 digits starting 6-9
- `email_format` — RFC-style basic format
- `dob_validity` — Valid date, age 1–100 years
- `dob_age_range` — Age 18–65 (WARN if outside)

### PIN & Address (`pincode_address.py`)
- `pincode_exists` — 6-digit format + India Post master
- `state_pin_match` — State matches PIN master
- `district_pin_match` — District/city matches PIN master
- `address_completeness` — address_line1 + city + state + pincode all present

### Duplicates (`duplicates.py`, LAN-scoped)
- `pan_duplicate` — Flag unless same UCID + different LANs
- `aadhaar_duplicate` — Idem
- `mobile_duplicate` — Idem
- `bank_account_duplicate` — Idem
- `name_dob_duplicate` — Idem
- `voter_id_duplicate` — Idem
- `address_duplicate` — Token-set Jaccard ≥0.85

### UCID (`ucid.py`)
- `ucid` — Union-find grouping (PAN, Aadhaar, Voter ID, Name+DOB, Bank Account, Address fuzzy)
  - Emits `ucid` + `ucid_size` columns
  - Flags `UCID_KYC_INCONSISTENT` if group has conflicting KYC values

### Email (`email.py`)
- `email_company_generic_domain` — Warn if gmail, yahoo, outlook, etc. (company should use business domain)

### Bank Account (`bank_account.py`)
- `bank_account_invalid_length` — Error if not 9–18 digits

### Beneficiary (`beneficiary.py`)
- Stable customer ID + deterministic grouping

---

## Column Mapping & Profiles

### Mechanism

1. **SchemaMap** (in `loader.py`) with per-report YAML (e.g., `customer_master.yaml`)
   ```yaml
   report_type: customer_master
   columns:
     customer_id:
       aliases: [customer_id, cust_id, client_id, borrower_id]
       required: true
       dtype: str
     pan:
       aliases: [pan, pan_no, pan_number]
       required: false
       dtype: str
     # ... 24 fields total
   ```

2. **Confidence scoring** (`score_header_match()`)
   - Exact alias match = 100%
   - Fuzzy via `difflib.SequenceMatcher.ratio()` for partial matches
   - Display % in UI; auto-select if ≥80%

3. **Saved profiles** (table: `mapping_profiles`)
   - On confirm: compute header_signature = SHA256(sorted(raw_headers))
   - Save (report_type, header_signature, mapping_json, engagement_id, created_by)
   - On future matching headers: auto-apply, no user re-mapping

---

## Aadhaar Handling (Non-Negotiable)

**Never:**
- Store full Aadhaar in any output CSV, database, or file
- Display full Aadhaar in UI or logs
- Use raw Aadhaar as key in joins

**Always:**
- Hash: `salted_hash = SHA256(salt + raw_aadhaar)`
- Display masked: `XXXXXXXX1234` (last 4 digits only)
- Use hash for dedup, not full value

**Applies to:** All outputs (wide CSV, long CSV, Excel workpaper), all UI pages, debug logs.

---

## Commands & Development

```bash
# Environment setup
python -m venv .venv
source .venv/bin/activate          # Unix/Mac
# or
.venv\Scripts\activate              # Windows

pip install -e ".[dev]"             # Editable install with dev dependencies

# Run app
uvicorn app.main:app --reload       # Auto-reload on file change
# Open http://localhost:8000 → login (admin/admin123)

# Lint & format
ruff check .                         # Check for issues
ruff check . --fix                   # Auto-fix (safe rules)
black .                              # Format code

# Tests
pytest                              # Full suite
pytest tests/test_kyc_format.py -v # Single module
pytest -k verhoeff                  # Single test by keyword
pytest -m perf                      # Slow perf test (5M rows, opt-in)

# Verify data survival
python -c "from fcmr_core.catalog import store; store.init_catalog()" # Twice → no data loss
```

---

## Configuration

Environment variables (or defaults in `fcmr_core/config.py`):

```bash
FCMR_DATA_DIR              # Base data directory (default: ./data)
FCMR_AADHAAR_HASH_SALT    # Salt for Aadhaar hashing (keep secret, ~32 chars)
FCMR_SESSION_SECRET       # FastAPI session secret (keep secret, ~32 chars)
FCMR_MAX_UPLOAD_BYTES     # File size limit (default: 2 GB = 2147483648)
FCMR_ROWS_PER_CHUNK       # Streaming chunk size (default: 10000)
```

---

## Testing Strategy

### Unit Tests
- `test_kyc_format.py` — Pan, Aadhaar, Voter ID, Passport, DL, mobile, email, DOB format validators
- `test_duplicates.py` — Duplicate detection with LAN scoping
- `test_ucid.py` — Union-find grouping, KYC consistency
- `test_pin_master.py` — PIN existence, state/district match
- `test_sampling.py` — Stratification, ICAI table, seeded selection

Each test uses curated fixtures (valid/invalid values, edge cases).

### Integration Tests
- Upload → ingest → map → run → wide CSV
- Verify all 27 rules execute
- Verify Aadhaar is hashed (not full) in output
- Verify wide CSV + long CSV generated

### Perf Test (marked `@pytest.mark.perf`)
- Generate synthetic 5M-row customer master with seeded defects
- Run full pipeline → verify exceptions match seed
- Assert peak memory < 8 GB on 15 GB machine

### Data Survival Test
- Call `init_catalog()` twice → assert all rows preserved
- Verify schema is additive (only `ALTER TABLE ... ADD COLUMN`, no `DROP`)

---

## Known Limitations & Future Work

- **Single admin** — No role-based access control (doable in Phase 8)
- **Desktop-only** — Not multi-tenant SaaS (no API key auth, no multi-workspace isolation beyond engagement)
- **Local file storage** — No S3/cloud sync (keeps data on laptop; git never touches `data/`)
- **Column mapping** — Deterministic fuzzy match via difflib; not ML-based (intentional for auditability)
- **Sampling** — ICAI table hard-coded; not configurable per engagement (doable)

---

## Deployment

### Single-User Desktop (Only Supported Model)

1. **Clone repo:**
   ```bash
   git clone https://github.com/ihbsandeepreddy/FCMR.git
   cd FCMR
   ```

2. **Install:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. **Run:**
   ```bash
   uvicorn app.main:app
   ```

4. **Access:**
   - Open http://localhost:8000
   - Login: admin / admin123

5. **Persistence:**
   - `data/` directory (gitignored) persists across restarts
   - `data/catalog.duckdb` is the single source of truth
   - `git pull` never deletes user data (additive migrations only)

### Multi-User? Cloud? Not supported.
- Engagement model is per-user (no collaboration)
- No API key auth or OAuth
- No containerization or k8s
- No S3 or cloud storage
- If needed: fork and redesign auth/catalog (beyond scope of SanGir Automations)

---

## Common Tasks

### Add a New Rule
1. Create function in appropriate module (e.g., `rules/email.py`)
2. Decorate with `@register(rule_id, description)`
3. Function signature: `rule(df: pl.DataFrame) -> pl.DataFrame`
4. Return df with 3 new columns: `_exc_{rule_id}_status`, `_exc_{rule_id}_code`, `_exc_{rule_id}_desc`
5. Import in `rules/registry.py`
6. Test with fixtures

### Add a New Report Type
1. Create YAML in `schemas/` (e.g., `disbursement.yaml`)
2. List canonical fields + aliases + required/dtype
3. Reference in ingestion logic
4. Column mapping auto-detects on upload

### Update Schema Safely
- Only `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE ... ADD COLUMN`
- Never `DROP COLUMN` or `DROP TABLE`
- Test: run `init_catalog()` twice, assert data preserved

### Deploy to Another Machine
- Same process: clone, venv, pip install, uvicorn
- Copy `data/` directory to new machine (if migrating data)
- Or start fresh with new `data/` directory

---

## References

- **ICAI Audit Sampling Guidance** — 95% confidence attribute table
- **ISA 530** — Audit Sampling (IAASB international standard)
- **RBI KYC Guidelines** — Know Your Customer requirements for NBFC
- **NFRA Fraud Risk Indicators** — Focus areas for loan audit
- **India Post PIN Master** — Bundled reference data

---

## Desktop Packaging & Updates (Phase 7+)

The app can be deployed as a standalone Windows desktop application via:

- **PyInstaller** freezes the Python backend into a standalone `.exe` (no Python runtime required)
- **Electron** wraps the FastAPI backend and opens it in a BrowserWindow
- **electron-updater** checks a public GitHub releases repo for new versions
- **GitHub Actions** automates builds and releases on version tags (`v*.*.*`)

For details on building, releasing, and distributing the desktop app, see:

- `docs/RELEASE_PROCESS.md` — Release workflow and setup
- `docs/USER_GUIDE.md` — End-user documentation
- `docs/INFRASTRUCTURE.md` — Full desktop & infrastructure specification
- `.github/workflows/release.yml` — Automated build-and-release CI

The web app (FastAPI + Jinja2) remains unchanged; the desktop shell simply wraps it.

---

## License & Attribution

This product was built as Phase 0–6 of SanGir Automations (audit core), with Phase 7+ desktop infrastructure by Sandeep Reddy (ihbsandeepreddy@gmail.com) with Claude Code assistance.

**Last updated:** 2026-06-18
