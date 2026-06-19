# SanGir Automations (FCMR)

Deterministic audit-analytics web tool for NBFC loan-portfolio validation —
KYC & data-quality checks, duplicate/UCID detection, PIN/address validation, ICAI-sampled
Excel audit workpapers, and EAD/ECL file consolidation. **No AI/LLM; fully deterministic.**

## Quick start

```bash
# Windows one-click: sets up venv, pulls latest, runs on :8000
start.bat

# Manual (Python 3.11+)
python -m venv .venv && .venv\Scripts\activate      # or: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload                        # http://localhost:8000

pytest -m "not perf"                                 # tests
```

Default login: `admin` / `admin123`.

## Documentation

📘 **All project documentation lives in [`CLAUDE.md`](CLAUDE.md)** — the single source of
truth for infrastructure, data model, the rules engine, the UI/design system, deployment
(local + Vercel), configuration, and the decision log. Read it before making changes.

## License

Apache-2.0.
