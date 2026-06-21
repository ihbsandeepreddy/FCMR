# SanGir Automations (FCMR) — Handoff (v0.1.38 production-hardening pass)

This document hands off the **production-hardening pass** done on branch
`claude/gifted-planck-p1n3ul`. It covers what changed, how to apply it, how to verify it, and
the **remaining roadmap** (with the items that need owner sign-off before coding).

---

## 1. How to apply the patch

The branch could not be pushed from the work environment (the git proxy returns **HTTP 403**),
so the work is delivered as a patch. **Base:** these patches apply on top of the pre-pass branch
tip `origin/claude/gifted-planck-p1n3ul` (the state before this pass began).

**Option A — apply as commits (preserves the 17 commits + messages):**
```bash
git fetch origin
git checkout claude/gifted-planck-p1n3ul       # pre-pass tip on origin
git am sangir_v0.1.38_hardening.patch          # mbox produced by git format-patch
```

**Option B — apply as a single diff (one squashed change):**
```bash
git checkout claude/gifted-planck-p1n3ul
git checkout -b sangir-hardening
git apply --index sangir_v0.1.38_hardening.diff
git commit -m "SanGir v0.1.38 production-hardening pass"
```
Use the `.patch` (mbox, `git am`) for the individual commits; use the `.diff` for the net change.

> If `git am` conflicts because your base differs, fall back to Option B (`git apply --3way`).
> Re-sign after applying if your org requires verified commits:
> `git rebase --exec "git commit --amend --no-edit --reset-author" <base>`

---

## 2. Environment setup & verification

```bash
python -m venv .venv && . .venv/bin/activate     # Python >= 3.11
pip install -e ".[dev]"

# tests are hermetic (tests/conftest.py sets a temp data dir + test secrets)
pytest -m "not perf" -v        # full CI suite
pytest -m perf -v              # slow e2e workpaper test
ruff check . && black --check .

# run the app
export FCMR_SESSION_SECRET=dev-secret FCMR_AADHAAR_HASH_SALT=dev-salt
uvicorn app.main:app --reload  # http://localhost:8000  (admin / admin123)
```
**Status at handoff:** `224 passed`, `ruff` clean, `black` clean.

New env override: **`FCMR_DATA_DIR`** now relocates the data root (catalog/outputs/logs) — useful
for isolated runs and tests.

---

## 3. What changed (16 commits, all tested)

Bug IDs reference the original hardening plan (WS1/WS2 = backend/web bug fixes).

| Area | Fix |
|---|---|
| **Rules — correctness** | **C1** `ucid` now runs *before* the duplicate rules in `run_pipeline`, so "same UCID + distinct LAN ⇒ OK" scoping works — legitimate multi-loan customers are no longer flagged as ERROR duplicates. |
| | **C3** beneficiary fallback key is deterministic again (was `id()`); **M1** leap-year-correct age. |
| **Privacy** | **H1** full Aadhaar is masked (`XXXXXXXX`+last4) in the downloadable wide CSV (invariant #2). |
| **Web** | **B1** run-detail page renders for failed/pending/running/cancelled runs (was a 500); **M2** Lorenz/KYC/duplicate charts now render (read from the wide CSV). |
| | **B2** uploads/runs can't be orphaned without an engagement; **B6** login shows an inline error; **B4** duplicate column mappings rejected; **B5** empty/header-only CSV fails clearly; **B7** ingestion error persisted + shown; **B8** dead `/dashboard/ead/consolidate` links repointed. |
| **Rule selection** | **C2/B3** per-engagement "disable rules" works end-to-end (route added, store getter fixed, subtracted from the run, checkboxes pre-checked). |
| **EAD (signed off)** | re-enabled all 8 EAD summary reports (`if result` on a DataFrame raised) and unblocked the **EAD workpaper** (a `/` in a sheet title made it never build); **H2** numeric casts so string-typed `ead`/amounts don't collapse summaries. |
| **Config/store** | **M3** honor `FCMR_DATA_DIR`; **L1** parameterize the parquet path in `store_upload_data`. |
| **UI/CSS** | **B9** define undefined `--fg`/`--bg-alt`; **B10** add `.badge-cancelled/-info/-warning/-success`. |
| **Desktop** | **D1** platform-aware backend exe name in `electron/main.js`; **D4** `itsdangerous` PyInstaller hidden import. |
| **Tests** | P0 golden safety nets (`test_ead_baseline_golden`, `test_cm_rules_golden`), hermetic `conftest.py`, `test_web_e2e`, `test_imports`, `test_rules_empty_inputs`, `test_sampling`, `test_vercel_secret`, plus `test_duplicates_ucid_scope`, `test_beneficiary`, `test_aadhaar_masking`; relocated the stray root e2e test into `tests/`. |
| **Docs** | CLAUDE.md header reconciled (v0.1.38). |

Commit list (oldest → newest): `451dba8, 23c6223, e1c1b16, 86cecc2, 3162e01, 29654a9, a7c35dd,
a42a339, 466da7a, 32b1dfe, 87286e4, 803d035, 8f03dc4, 91afe46, fa26143, 8b59902`.

---

## 4. Guardrails / conventions (keep these)

- **EAD module is a frozen baseline.** `fcmr_core/analytics/ead_analytics.py`, `ead_summary.py`,
  `app/api/ead_analytics.py`, `app/web/templates/ead_run_detail.html`, and the `ead_runs` table
  are built on *additively only*. The EAD changes in this pass were explicitly signed off and are
  guarded by `tests/test_ead_baseline_golden.py` (report set + columns + row counts locked).
- **Invariants:** no AI/LLM; Aadhaar salted-hash + masked; deterministic reproducibility;
  additive-only catalog migrations (guarded `ALTER … ADD COLUMN`, never drop); `apply_duckdb_limits`
  on every analytics DuckDB connection; runs/uploads are engagement-scoped.
- **Quality gate:** keep `ruff`/`black` clean (line length 100) and the suite green per change.
- **Golden tests are the safety net** — if `test_cm_rules_golden` or `test_ead_baseline_golden`
  changes, it must be an intentional, explained re-baseline (esp. before/after the perf work).
- Follow CLAUDE.md **§22 change-checklist-by-layer**; update CLAUDE.md in the same change.

---

## 5. Known issues / environment notes

- **Push blocked (HTTP 403):** the work env's git proxy rejected pushes — hence this patch.
- **Commit signing:** the work env signs via a sign-only helper (`/tmp/code-sign`) and has no
  `ssh-keygen`, so signatures can't be *verified locally* (`git %G?` shows `N`). The commits do
  carry SSH signatures; GitHub verifies server-side against the account's registered key.
- **EAD `product`/`sbu` reports** error on canonical-only frames ("unable to find column
  scheme_id/sbu") — likely a real column-reference mismatch in those two EAD reports. Left for a
  dedicated, signed-off EAD pass (frozen module).
- **Desktop builds cannot be produced/verified** in the work env (Linux, no Windows toolchain).
  Desktop changes are code-level only; the `.exe`/installer is a release-CI artifact.

---

## 6. Remaining roadmap (NOT done — prioritized)

### 6a. Small, low-risk leftovers
- **Doc/category nit:** `address_completeness` is listed under the `missing_data` category but is
  registered in `pincode_address.py` — reconcile the `CATEGORIES` grouping or the doc; confirm the
  "31 rules" count.
- **Desktop D2/D3/D5:** D2 backend-crash dialog in `electron/main.js` (currently a 90s hang before a
  generic timeout); D3 `_resource_root()` helper in `config.py` for frozen template/static paths
  (likely already correct in onedir builds — verify on a real frozen build); D5 cross-platform
  orphan-reap via `psutil` in `desktop_backend.py` (currently Windows-only).
- **Release/CI & docs:** confirm `.github/workflows/release.yml` is Windows-only by design; correct
  CLAUDE.md §13 commands (PyInstaller output is `dist/sangir-backend/sangir-backend.exe`; add real
  `npm` scripts or fix the doc; drop the `--reload` claim).
- **WS8 reviews:** run `/code-review` (high) and `/security-review` on the diff before merge.

### 6b. Performance for ~10M rows (WS3 — big)
Lock output with the goldens first, then keep byte-identical:
1. Vectorize the per-row Python loops in `rules/kyc_format.py`, `missing_data.py`,
   `pincode_address.py`, and the post-self-join annotation loops in `duplicates.py` → Polars
   expressions (`str.contains`/`str.extract`; PIN/state/district via joins to the PIN master).
2. Push cross-row work into DuckDB SQL; reuse one connection/registration across the 7 duplicate
   rules; `apply_duckdb_limits` everywhere.
3. Memory: move ingestion→rules toward Polars `scan_parquet`/streaming; cache `get_upload_df`.
4. Fuzzy address (Jaccard) can't run exhaustively at 10M rows → **deterministic blocking** (e.g.
   pincode + first normalized token), bounded buckets, Jaccard within blocks. Keep the cap as a
   backstop.
5. Paginate / cap large UI tables (top-N + "download full").

### 6c. Bolder UI refresh (WS4 — within the warm-beige design system, no new fonts/hex)
Reusable flash/toast; active-engagement chip in the topbar + active-card highlight; consistent
loading/empty/error states (incl. a no-engagement dashboard state and poller connection-loss caps);
discoverability (sidebar links for `/audit` + admin-gated `/users`; route the dashboard Run button by
report_type); accessibility (`:focus-visible`, `aria-label`s); responsive media queries; richer
dashboard/cards/tables; replace hard-coded hex in `settings.html`/`user_management.html` with vars.

### 6d. Two-engine audit-deliverable upgrade (the larger approved brief — gated)
Keep EAD and Customer Master as **separate engines + dashboards**; EAD additive-only.
1. **ICFR sampling redesign (CRITICAL, gated):** the current sampler falls back to `√N` when the
   exception rate exceeds the ICAI table's 0–20% bands (→ ~1,400-row samples on large, dirty files).
   Replace with **max-N-per-exception (default 10), stratified by available variety keys** (severity
   always; +geography; +rule sub-type; +value/product/branch band *only when those columns exist*),
   seeded by `SHA256(engagement:run:code)`, with the SA 530 basis printed on TOC/TOD. **Present the
   algorithm to the owner for sign-off before coding.** Determinism test already in place.
2. **Control-ref catalog:** stable codes (e.g. `CM-KYC-C001`) → objective/assertion/source-doc,
   surfaced on every working-paper sheet (none exist today).
3. **Working-paper overhaul:** rebuild the Lead sheet (Big-4 layout), add analysis columns to
   TOC/TOD, make Detailed-Exceptions one-row-per-exception, and route ALL sheets (both workbooks)
   through one `excel_style` house style + cover sheet + hyperlinked index. EAD workbook edits are
   ⚑ per-edit sign-off.
4. **CM schema additions + analytics:** add optional canonical columns (amount/product/branch/dates/
   exposure) with aliases, `NOT_RUN`-guard each analytic that needs them; build statutory CM summary
   reports + charts (concentration/Lorenz, geo & product mix, vintage, KYC-expiry, duplicate
   clusters, risk heat map) — DuckDB-aggregated SVG, render aggregates only.
5. **International best-practice analytics + WP template research (gated):** present a shortlist for
   approval before building.
6. **FCMR → SanGir rename:** cosmetic strings now (most UI already says "SanGir"); the structural
   rename (`fcmr_core` package, `FCMR_` env prefix with back-compat alias, persisted
   `fcmr_customer_key`/`fcmr_group_id` columns) is a separate, test-covered, migration-aware change.
7. **Product-review backlog** (impact×effort) toward $100M-product quality — owner picks before build.

> Stack note: this app is **server-rendered FastAPI + Jinja2 + htmx + Polars/DuckDB**, wrapped for
> desktop by Electron + PyInstaller (there is **no** React/TS/Vite). Build new dashboards/charts in
> the existing stack (Jinja2 + htmx + `reporting/charts.py` SVG), not as an SPA.

---

## 7. Key files
- Rules/engine: `fcmr_core/rules/registry.py`, `rules/duplicates.py`, `rules/beneficiary.py`,
  `rules/kyc_format.py`; reporting `reporting/builder.py`, `reporting/workpaper.py`,
  `reporting/excel_style.py`, `reporting/charts.py`; sampling `sampling/*`.
- EAD (frozen): `analytics/ead_analytics.py`, `analytics/ead_summary.py`, `app/api/ead_analytics.py`.
- Web: `app/api/{runs,uploads,settings,auth,downloads}.py`; templates + `static/css/main.css`.
- Catalog/config: `fcmr_core/catalog/store.py`, `fcmr_core/config.py`.
- Desktop/build: `electron/main.js`, `desktop_backend.py`, `build/sangir-backend.spec`.
- Tests: `tests/` (start with `conftest.py`, `test_*_golden.py`, `test_web_e2e.py`).
