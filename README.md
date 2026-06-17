# FCMR — Loan Audit Data Analytics

Production-grade, deterministic data-analytics tool for NBFC loan audit processes.

## What it does

1. **Ingest** large CSV exports (LMS, collection, disbursement, technical write-off, customer master) and convert them to fast, low-memory Parquet.
2. **Validate** the customer master with hard-coded Python logic — KYC format checks, duplicate detection, PIN/address validation — producing a CSV with an exception description against every line item.
3. **Web UI** to upload, trigger runs, view summaries, and download results.

No AI/LLM is used. All logic is deterministic and unit-tested.

## Quick start

```bash
# 1. Clone and install (Python 3.11+)
git clone https://github.com/ihbsandeepreddy/FCMR.git
cd FCMR
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Run the app
uvicorn app.main:app --reload
# Open http://localhost:8000

# 3. Tests
pytest
pytest -m perf   # slow 5M-row end-to-end test (opt-in)
```

## Phase 1 analytics (customer master)

| Check | Detail |
|---|---|
| PAN format | `^[A-Z]{5}[0-9]{4}[A-Z]$` + 4th-char entity type |
| Aadhaar format | 12 digits + Verhoeff checksum; stored/shown masked only |
| Voter ID | `^[A-Z]{3}[0-9]{7}$` |
| Passport | `^[A-PR-WY][0-9]{7}$` |
| Driving Licence | State-code prefix + structural pattern |
| PIN authentication | Existence + city/district/state match vs bundled India Post master |
| Address validation | Completeness checks, PIN/region consistency |
| KYC duplicates | Shared PAN, Aadhaar, mobile, bank account; normalized name+DOB |
| Beneficiary tagging | Stable internal customer key + group IDs |

## Output files

- **`<run_id>_wide.csv`** — one row per input record with `overall_status`, `exception_codes`, `exception_descriptions` (pipe-joined).
- **`<run_id>_long.csv`** — one row per (record, exception) for drill-down.

## Tech stack

- **Polars** (streaming ingest & per-row rules) + **DuckDB** (cross-row joins / dedup at scale)
- **Parquet** as the working format (CSV → Parquet once on ingest)
- **FastAPI** + Jinja2 HTML + htmx (backend-only; wrappable as desktop app later)

## License

Apache-2.0 — see [LICENSE](LICENSE).
