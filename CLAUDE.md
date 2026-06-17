# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Status: this file is written from the approved Phase 1 design plan ahead of the code landing.
> As modules are implemented, keep the commands and paths here in sync with reality.

## What this is

FCMR is a **production-grade, deterministic** data-analytics tool supporting an NBFC's loan
audit process. It ingests large operational CSV exports (LMS, collection, disbursement,
technical write-off, customer master, and other reports), converts them to a fast low-memory
working format, and runs **hard-coded Python validation/analytics** on the customer master,
emitting CSV output with an exception description against every line item.

Two constraints shape almost every decision:
- **No AI/LLM anywhere.** All validation/analytics is deterministic, hard-coded, unit-tested
  Python. Do not introduce model-based matching, embeddings, or LLM calls.
- **5M+ row CSVs must process on a ~15 GB laptop without blowing up memory.** Correctness is
  prioritized over speed. Never load a full input CSV into memory.

## Tech stack & why

- **Python 3.13.**
- **Polars** (lazy/streaming) for ingest and per-row rules; **DuckDB** for cross-row work
  (duplicate self-joins, PIN-master joins, group-bys) that may exceed RAM. Prefer these over
  Pandas — Pandas at 5M rows on this hardware is the failure mode this design exists to avoid.
- **Parquet** is the canonical working format. Raw CSV is converted to Parquet **once** on
  ingest; all analytics read Parquet, never the original CSV.
- **FastAPI + Uvicorn** backend with **Jinja2** HTML templates (+ light vanilla JS / htmx).
  The backend is deliberately decoupled from the UI so it can later be wrapped as a desktop
  app without a rewrite — keep business logic in `fcmr_core`, not in route handlers.

## Commands

> Targets per the plan; verify against `pyproject.toml` once it exists.

```bash
# Environment (Python 3.13 via miniconda is already on this machine)
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -e ".[dev]"

# Run the web app (FastAPI + Uvicorn)
uvicorn app.main:app --reload

# Lint / format
ruff check .
black .

# Tests
pytest                              # full suite
pytest tests/test_kyc_format.py     # one file
pytest -k verhoeff                  # one test by keyword
pytest -m perf                      # the 5M-row end-to-end perf test (slow; opt-in marker)
```

## Architecture (the big picture)

The dependency direction is **`app/` → `fcmr_core/`**. Route handlers stay thin; all logic
lives in `fcmr_core` so it is reusable from a future desktop shell and directly unit-testable.

```
app/                     FastAPI app + HTML UI (thin: upload -> ingest -> run -> view -> download)
fcmr_core/
  config.py              pydantic-settings: paths, row/chunk limits, salts
  ingestion/             streaming CSV -> Parquet, structural validation, malformed-row quarantine
  schemas/               canonical schema + per-report column-mapping YAMLs
  rules/                 deterministic rule framework + customer-master rule modules
  reference/             bundled India Post PIN master (Parquet) + loader
  reporting/             exception CSV builders (wide per-line-item + long per-exception)
  catalog/               upload/run tracking store (DuckDB/SQLite)
data/                    .gitignored: uploads/, parquet/, outputs/
```

### Ingestion pipeline
Each report type maps to a canonical schema via a **column-mapping YAML** in `schemas/` — this
is the seam that absorbs messy real-world headers. Missing mandatory columns are **reported,
not crashed on**. CSVs are streamed (`scan_csv` / DuckDB `read_csv_auto`) straight to Parquet;
malformed rows are quarantined to a rejects CSV and summarized in an ingestion-report CSV
(total / accepted / rejected-with-reason / coercions). When touching ingestion, preserve the
streaming property — no full-frame materialization.

### Rule framework (Phase 1 = customer master)
A rule is a **pure function over a Polars/DuckDB frame** returning per-row
`(status, exception_code, description)`. Rules self-register in `rules/registry.py` and run as
a pipeline. To add a check, add a rule function and register it — don't special-case it in the
runner. The four module groups: KYC format (PAN, Aadhaar+Verhoeff, Voter ID, Passport, DL,
mobile, email, DOB), PIN+address validation (existence + city/district/state consistency vs the
India Post master), duplicate detection (shared PAN/Aadhaar/mobile/bank-acct; normalized exact
name+DOB), and beneficiary tagging (stable internal ID + deterministic group keys).

### Aadhaar handling — non-negotiable
Never persist or display a full Aadhaar number. Store only a **salted hash** for dedup; all
outputs and UI show the **masked** form (`XXXXXXXX1234`). Any new code path that touches Aadhaar
must uphold this.

### Output contract
Primary output is a **wide per-line-item CSV**: one row per input record plus `overall_status`,
`exception_count`, `exception_codes` (pipe-joined), `exception_descriptions` (pipe-joined). A
secondary **long CSV** has one row per (record, exception) for drill-down. Both are written to
`data/outputs/<run_id>/` and downloadable from the UI.

## Testing expectations specific to this project
- Each KYC validator has curated valid/invalid fixtures (Aadhaar Verhoeff, PAN entity char,
  PIN-master hit/miss, etc.).
- A synthetic data generator produces a 5M-row customer master with **seeded defects**; the perf
  test asserts the exception CSV flags exactly those defects and peak memory stays bounded.
