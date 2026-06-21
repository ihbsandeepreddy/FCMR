# Product Backlog — SanGir Automations (FCMR)

**Last Updated:** 2026-06-21  
**Version:** 0.1.31+  
**Status:** Living document — priorities shift with deployment context

This backlog captures product work that is NOT in the current scope (Part A/B infrastructure). Items are organized by impact/priority within each category. No issue is "nice-to-have"—all have audit, UX, reliability, or compliance implications.

---

## Priority Tiers

- **P0 (Blocker):** Prevents production use or audit defensibility
- **P1 (Critical):** Major UX friction, data loss risk, or compliance gap
- **P2 (High):** Impacts auditor efficiency, team scaling, or trust
- **P3 (Medium):** Polish, edge-case handling, future-proofing

---

## 1. User & Auth (P1–P2)

### P1: Change-Password Endpoint
**Problem:** Dashboard shows "Change password on first login" but no endpoint exists.  
**Impact:** Auditors cannot change admin password; security posture unclear.  
**Effort:** Small (1 route + password validation + session re-auth)  
**Risk:** Low (isolated)  
**Implementation:** Add `POST /api/auth/change-password` with PBKDF2 + login-gated.

### P2: User Management UI
**Problem:** No way to add/revoke users; single hard-coded `admin:admin123`.  
**Impact:** Scaling to multi-auditor teams requires manual DB edits.  
**Effort:** Medium (user CRUD routes + admin panel + permissions check)  
**Risk:** Medium (auth layer redesign)  
**Prerequisite:** Change-password endpoint.

### P2: Session Timeout & Auto-Logout
**Problem:** Sessions persist indefinitely; no idle timeout.  
**Impact:** Shared terminals remain logged in; audit trail gaps.  
**Effort:** Medium (middleware + session TTL config + JavaScript warning)  
**Risk:** Low (graceful re-login)

---

## 2. UX Consistency & States (P1–P2)

### P1: Empty/Loading/Error States
**Problem:** Many pages (dashboard, run detail, settings) don't gracefully handle empty data or API failures.  
**Impact:** Auditors see blank screens or cryptic errors; unclear whether to retry.  
**Effort:** Medium (add spinner, fallback UI, error messages across 5+ templates)  
**Risk:** Low (template-only)  
**Note:** Settings page shows loading spinner (good pattern); apply to other endpoints.

### P2: Form Validation & Feedback
**Problem:** Upload form, column mapping, consolidation UI lack client-side validation and inline error messages.  
**Impact:** Auditors submit invalid data, wait for backend error, re-submit.  
**Effort:** Medium (htmx validation + client-side checks)  
**Risk:** Low (progressive enhancement)

### P2: Modal/Confirmation Dialogs
**Problem:** Destructive actions (e.g., "Re-ingest upload", "Delete run") don't confirm; undo is impossible.  
**Impact:** Accidental data loss (runs, exception analyses).  
**Effort:** Small (modal component + route guards)  
**Risk:** Low (isolated)

---

## 3. Error Handling & Logging (P1–P2)

### P1: Fail-Safe Analytics Gracefully
**Problem:** If B4/B5 analytics fail (missing column, malformed data), they silently skip; no dashboard warning.  
**Impact:** Auditors trust incomplete analysis without knowing.  
**Effort:** Small (add flags to context, show "N/A — missing data" cards)  
**Risk:** Low (UI only)

### P2: Workpaper Generation Failures
**Problem:** If workpaper build fails mid-way (OOM, disk full), user gets error but no partial output.  
**Impact:** Auditor loses all workpaper, must re-run.  
**Effort:** Medium (streaming write + resume-able generation)  
**Risk:** Medium (file I/O)

### P2: Centralized Error Alerting
**Problem:** Errors appear in logs only; no in-app alerts to auditors.  
**Impact:** Issues silently accumulate; operators unaware.  
**Effort:** Medium (error banner UI + error logging to session)  
**Risk:** Low (add notification)

---

## 4. Performance & Scaling (P2–P3)

### P2: UCID O(n²) Pairwise Matching
**Problem:** UCID union-find does pairwise `_should_connect` check on all customer pairs.  
**Impact:** Real ceiling ~tens of thousands; "5M-row" claim is not realistic.  
**Effort:** High (keying/blocking before pairwise, union-find optimization)  
**Risk:** Medium (core logic redesign)  
**Workaround:** Document realistic row limits; alert if input > 100k rows.

### P2: Address Duplicate O(n × avg_tokens) Index Scan
**Problem:** Address dedup scans all candidate pairs; can be slow on large datasets.  
**Status:** Already optimized in v0.1.23 (inverted token index + Jaccard filtering).  
**Remaining:** Benchmark on real datasets; consider skip if file > 1M rows.

### P3: Dashboard Chart Rendering Perf
**Problem:** Lorenz/KYC/Duplicates charts render via Polars aggregation in endpoint.  
**Impact:** On large datasets (100k+ rows), endpoint latency may spike.  
**Effort:** Medium (pre-compute on background task + cache)  
**Risk:** Low (caching layer)

---

## 5. Data Validation & Completeness (P1–P2)

### P2: IFSC State-Code Validation
**Problem:** B4.4 bank anomalies use simplified IFSC format check + substring state match (not a lookup table).  
**Impact:** False positives on state mismatch (e.g., branch in Delhi but state = "UT").  
**Effort:** Small (add India state-code lookup; ~37 states)  
**Risk:** Low (isolated rule)

### P2: Aadhaar Checksum Validation
**Problem:** Aadhaar format check validates Verhoeff checksum; no edge cases known.  
**Status:** Good (test coverage exists).  
**Remaining:** Verify against RBI updates (checksums change periodically).

### P3: PAN Format Strictness
**Problem:** PAN format check uses simple regex; no validation of state code (position 3–4) or industry code.  
**Impact:** Invalid PANs may pass; auditor must manually flag.  
**Effort:** Small (PAN state/sector lookup)  
**Risk:** Low

---

## 6. Audit Trail & Traceability (P1–P2)

### P1: Audit Log for Run Lifecycle
**Problem:** No audit trail of who ran what, when, with which rules.  
**Impact:** Cannot reconstruct analysis history; compliance gap.  
**Effort:** Medium (audit log table + middleware + dashboard view)  
**Risk:** Low (logging-only)

### P2: Exception Code Mapping Source Doc
**Problem:** Exception codes map to source documents (NFRA, RBI, ISA 530) only in workpaper.  
**Impact:** Dashboard doesn't show the audit source; auditor must check workpaper.  
**Effort:** Small (add source-doc metadata to rules; render in dashboard)  
**Risk:** Low (metadata + template)

### P2: Long CSV Row Traceability
**Problem:** Long CSV ties exceptions to rows via `_row_num`; no customer context.  
**Impact:** Auditor must cross-reference wide CSV to see customer ID.  
**Effort:** Small (join customer_id into long CSV at export)  
**Risk:** Low

---

## 7. Exportability & Reporting (P2–P3)

### P2: Additional Export Formats
**Current:** CSV (wide/long) + workpaper (Excel).  
**Requested:** PDF report, JSON API for programmatic access.  
**Effort:** Medium (PDF template + JSON endpoint)  
**Risk:** Low

### P3: Consolidated Data Download (EAD & CM)
**Problem:** Consolidation UI shows "Download Excel/CSV" for merged multi-file sources.  
**Status:** Works (§9 consolidation pattern).  
**Remaining:** Performance test on 100M-row consolidated datasets.

---

## 8. Configuration & Flexibility (P2–P3)

### P2: Fuzzy-Match Threshold Tuning
**Current:** Live config at `/settings` (default 0.6).  
**Status:** Works.  
**Remaining:** Audit guidance—when to adjust threshold; no docs.

### P3: Hardware-Tier Detection & Overrides
**Current:** Auto-detect via RAM; override via `FCMR_HW_TIER` env var.  
**Status:** Works; limitations documented.  
**Remaining:** Dashboard warning if detected tier < required (e.g., "Low-tier detected; limit uploads to < 50k rows").

### P3: Rule Enable/Disable Per-Engagement
**Problem:** All 31 rules always available; no way to disable noisy/irrelevant rules.  
**Impact:** Auditors must filter post-run; wishful for high-volume engagement workflows.  
**Effort:** Medium (rule whitelist per engagement + store schema)  
**Risk:** Medium (schema change)

---

## 9. Reliability & Resilience (P2–P3)

### P2: Graceful Degradation on Partial Failure
**Problem:** If one analytics path fails (e.g., EAD reports), the entire run fails.  
**Impact:** Auditor must re-run entire analysis; loses partial results.  
**Effort:** Medium (per-path error handling + partial result output)  
**Risk:** Medium (transaction semantics)

### P2: Workpaper Timeout & Resume
**Problem:** Workpaper generation can OOM or timeout on large datasets (100k+ exceptions).  
**Impact:** No output; auditor has no recourse except reduce data.  
**Effort:** High (streaming write + resume-able generation)  
**Risk:** Medium (file I/O + cleanup)

### P3: Backup & Restore (Beyond Manual)
**Current:** Manual `create_backup()` API call (no UI).  
**Status:** Works for one-off backups.  
**Remaining:** Scheduled backups (cron), restore UI, versioning.

---

## 10. Documentation & Onboarding (P2–P3)

### P2: Auditor Quick-Start Guide
**Current:** CLAUDE.md is technical; no user-facing guide.  
**Impact:** New auditors struggle with engagement/upload/run workflow.  
**Effort:** Small (write `docs/QUICK_START.md`)  
**Risk:** None (docs-only)

### P2: Troubleshooting Guide
**Current:** `docs/TROUBLESHOOTING.md` covers DuckDB memory.  
**Missing:** Common issues (stuck runs, mapping failures, export errors).  
**Effort:** Medium (gather from support queries; document resolution)  
**Risk:** None

### P3: Rule Catalog Documentation
**Current:** 31 rules are self-documented in `CATEGORIES` and rule metadata.  
**Missing:** Per-rule guidance—when to run, how to interpret findings, what action to take.  
**Effort:** Medium (audit methodology doc)  
**Risk:** None

---

## 11. Known Limitations (Documented, Not Blocking)

See [CLAUDE.md §18](CLAUDE.md#18-known-limitations--scaling-notes) for current limits:

- Vercel deployment is ephemeral (not production-ready).
- UCID ceiling ~tens of thousands (not 5M).
- No change-password endpoint (despite UI notice).
- No multi-user or role-based access.
- Consolidation alignment grid is add/remove-free (minor UX).

These are **not P0 blockers** in v0.1.x (single-auditor, desktop-first, offline-capable model), but become **P1** if scaling to SaaS / multi-tenant.

---

## Prioritization Framework

**When to tackle each tier:**

| Tier | Trigger | Timeline |
|---|---|---|
| **P0** | Before production launch | Immediate |
| **P1** | Before multi-auditor or cloud deployment | Q3 2026 |
| **P2** | Quarterly (every 4 auditor-months of use) | Rolling |
| **P3** | Annual review; low-effort wins in spare cycles | Backlog |

---

## Next Steps

1. **Validate priorities** with audit team (P1–P2 alignment check).
2. **Estimate effort** for P1 items (change-password, error handling, UCID).
3. **Assign owners** for documentation (quick-start, troubleshooting).
4. **Schedule P1 work** before next engagement batch.

---

**Document History:**
- 2026-06-21: Initial backlog compiled post-Part-B release.
