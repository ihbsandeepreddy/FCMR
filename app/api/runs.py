"""Run (analytics execution) endpoints."""

from __future__ import annotations

import gc
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import psutil
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from fcmr_core.analytics.cm_analytics import (
    generate_aadhaar_coverage,
    generate_bank_account_anomalies,
    generate_coapplicant_concentration,
    generate_fraud_risk_flags,
)
from fcmr_core.analytics.cm_summary import (
    generate_cluster_distribution,
    generate_coapplicant_overlap,
    generate_data_quality_summary,
    generate_demographic_distribution,
    generate_duplication_summary,
    generate_geographic_distribution,
    generate_kyc_completeness,
    generate_lan_concentration,
)
from fcmr_core.catalog import store
from fcmr_core.config import settings
from fcmr_core.ingestion.pipeline import read_parquet
from fcmr_core.logging_setup import get_logger
from fcmr_core.reporting.aggregation import (
    aggregate_exception_codes,
    aggregate_missing_data,
    aggregate_status_counts,
)
from fcmr_core.reporting.builder import build_exception_csvs
from fcmr_core.reporting.charts import (
    build_bar_chart,
    build_donut_svg,
    build_duplicates_pie,
    build_kyc_completeness_bar,
    build_lorenz_curve,
)
from fcmr_core.reporting.workpaper import build_workpaper
from fcmr_core.rules.registry import (
    _ensure_rules_loaded,
    list_categories,
    list_rules,
    resolve_rule_ids,
    run_pipeline,
)
from fcmr_core.sampling.sample import select_sample

logger = get_logger("processing")

router = APIRouter()

# In-memory set of run IDs that have been requested to cancel.
_cancel_requests: set[str] = set()


class _RunCancelled(Exception):
    """Raised by the on_progress callback when a cancel is requested mid-pipeline."""


_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _resolve_run_selection(
    mode: str,
    categories: list[str] | None,
    rules: list[str] | None,
    disabled: list[str] | None = None,
) -> list[str] | None:
    """Resolve the run's rule selection, validating before any run row is created.

    Returns None for "run all" (with no engagement-disabled rules); otherwise a
    non-empty rule_ids list. Rules disabled for the engagement are always removed
    from the effective set so deselected categories never execute or appear in
    output. Raises 400 when the effective selection is empty.
    """
    disabled_set = set(disabled or [])
    if mode == "all":
        if not disabled_set:
            return None
        _ensure_rules_loaded()
        remaining = [m.rule_id for m in list_rules() if m.rule_id not in disabled_set]
        if not remaining:
            raise HTTPException(
                status_code=400, detail="All rules are disabled for this engagement."
            )
        return remaining

    rule_ids = resolve_rule_ids(categories or [], rules or [])
    if rule_ids is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No categories or rules selected. Either check some options and "
                "click 'Run Selected', or click 'Run All Rules'."
            ),
        )
    remaining = [r for r in rule_ids if r not in disabled_set]
    if not remaining:
        raise HTTPException(
            status_code=400,
            detail="Every selected rule is disabled for this engagement.",
        )
    return remaining


@router.get("/runs", response_class=HTMLResponse)
async def runs_list(request: Request):
    engagement_id = request.session.get("engagement_id")
    runs = store.list_runs_for_engagement(engagement_id) if engagement_id else []
    has_running = any(r["status"] in ("running", "pending") for r in runs)
    all_uploads = store.list_uploads(engagement_id=engagement_id) if engagement_id else []
    ready_uploads = [u for u in all_uploads if u["status"] == "ready"]
    categories = list_categories()
    disabled_rules = store.get_disabled_rules(engagement_id) if engagement_id else []
    return templates.TemplateResponse(
        request=request,
        name="runs_list.html",
        context={
            "runs": runs,
            "has_running": has_running,
            "ready_uploads": ready_uploads,
            "categories": categories,
            "disabled_rules": disabled_rules,
        },
    )


@router.post("/runs/start")
async def runs_start(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_id: str = Form(...),
    mode: str = Form("all"),
    categories: list[str] | None = Form(None),
    rules: list[str] | None = Form(None),
):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "ready":
        raise HTTPException(status_code=400, detail="Upload is not ready")

    # Validate selection BEFORE creating the run (no orphaned "running" run on 400).
    # Engagement-disabled rules are subtracted from the effective set.
    engagement_id = request.session.get("engagement_id")
    disabled = store.get_disabled_rules(engagement_id) if engagement_id else []
    rule_ids = _resolve_run_selection(mode, categories, rules, disabled)

    username = request.session.get("username")
    run_id = store.create_run(upload_id, engagement_id)
    store.update_run(run_id, status="running", started_at=_now())
    if rule_ids is not None:
        # Persist selected rules for display in run_detail
        store.update_run(run_id, selected_rules=json.dumps(rule_ids))

    # Log run start
    store.log_audit_event(
        action="run_started",
        target=run_id,
        detail=f"upload_id={upload_id}",
        username=username,
    )

    background_tasks.add_task(_run_analytics, run_id, upload_id, rule_ids)
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@router.post("/uploads/{upload_id}/run")
async def start_run(
    request: Request,
    upload_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Form("all"),
    categories: list[str] | None = Form(None),
    rules: list[str] | None = Form(None),
):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "ready":
        raise HTTPException(status_code=400, detail="Upload is not ready")

    # Validate selection BEFORE creating the run (no orphaned "running" run on 400).
    engagement_id = request.session.get("engagement_id")
    disabled = store.get_disabled_rules(engagement_id) if engagement_id else []
    rule_ids = _resolve_run_selection(mode, categories, rules, disabled)
    logger.info(
        "start_run mode=%s upload_id=%s categories=%s rules=%s resolved=%s",
        mode,
        upload_id,
        categories,
        rules,
        rule_ids,
    )

    run_id = store.create_run(upload_id, engagement_id)
    store.update_run(run_id, status="running", started_at=_now())
    if rule_ids is not None:
        # Persist selected rules for display in run_detail
        store.update_run(run_id, selected_rules=json.dumps(rule_ids))

    background_tasks.add_task(_run_analytics, run_id, upload_id, rule_ids)

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] not in ("running", "pending"):
        raise HTTPException(status_code=400, detail="Run is not in progress")
    _cancel_requests.add(run_id)
    return JSONResponse({"status": "cancel_requested"})


@router.get("/runs/{run_id}/status")
async def run_status(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse(
        {
            "status": run["status"],
            "progress_step": run.get("progress_step") or "",
            "progress_pct": run.get("progress_pct") or 0,
            "error": run.get("error") or "",
        }
    )


def _build_workpaper_background(run_id: str, upload: dict) -> None:
    """Pre-generate workpaper after analytics completes (best-effort background task)."""
    run = store.get_run(run_id)
    if (
        not run
        or run["status"] != "completed"
        or not run.get("wide_csv")
        or not run.get("long_csv")
    ):
        return

    engagement_id = run.get("engagement_id") or "default"
    engagement = store.get_engagement(engagement_id)
    if not engagement:
        engagement = {
            "engagement_id": engagement_id,
            "name": "Audit Engagement",
            "client_name": "—",
            "period_from": None,
            "period_to": None,
        }

    wide_path = Path(run["wide_csv"])
    long_path = Path(run["long_csv"])
    if not wide_path.exists() or not long_path.exists():
        return

    df = pl.read_csv(wide_path, infer_schema_length=0)
    population = len(df)
    exception_count = df.get_column("overall_status").ne("OK").sum()

    sample_records = select_sample(
        wide_path,
        engagement_id=engagement_id,
        run_id=run_id,
        population=population,
        exception_count=exception_count,
    )

    workpaper_path = build_workpaper(
        engagement=engagement,
        run=run,
        upload=upload,
        wide_csv_path=wide_path,
        long_csv_path=long_path,
        sample_records=sample_records,
        output_dir=settings.outputs_dir / run_id,
    )

    store.update_run(run_id, workpaper_path=str(workpaper_path))
    logger.info("workpaper_prebuilt run_id=%s path=%s", run_id, workpaper_path.name)


def _run_analytics(run_id: str, upload_id: str, rule_ids: list[str] | None = None) -> None:
    """Execute the full analytics pipeline and update the catalog when done."""
    import json

    def _check_cancel() -> None:
        """Raise _RunCancelled if a stop was requested."""
        if run_id in _cancel_requests:
            raise _RunCancelled()

    def _on_rule_progress(completed: int, total: int, rule_id: str) -> None:
        """Called by run_pipeline after each rule. Updates DB with real % progress."""
        _check_cancel()
        # Rules span 5% → 90% of the total progress range.
        pct = 5 + int((completed / total) * 85)
        label = f"Rule {completed}/{total}: {rule_id.replace('_', ' ')}"
        store.update_run(run_id, progress_step=label, progress_pct=pct)

    try:
        upload = store.get_upload(upload_id)
        logger.info("job_start run_id=%s upload_id=%s rule_ids=%s", run_id, upload_id, rule_ids)

        # Store the selected rules (None = all)
        selected_rules_str = json.dumps(rule_ids) if rule_ids else None
        store.update_run(run_id, selected_rules=selected_rules_str)

        _check_cancel()
        store.update_run(run_id, progress_step="Loading data file", progress_pct=2)

        # Pre-flight: warn if available RAM is below 2 GB before we start
        available_gb = psutil.virtual_memory().available / 1024**3
        if available_gb < 2.0:
            logger.warning(
                "low_ram run_id=%s available_gb=%.1f — processing will rely on DuckDB disk spill",
                run_id,
                available_gb,
            )

        # Data lives in DuckDB after ingestion; parquet is deleted post-import.
        try:
            df = store.get_upload_df(upload_id)
        except Exception:
            parquet_path = Path(upload["parquet_path"])
            if not parquet_path.exists():
                raise FileNotFoundError(
                    f"Data file not found at {parquet_path}. " "Please re-upload the CSV file."
                )
            df = read_parquet(parquet_path).collect()

        # Cast every column to string up-front. DuckDB infers numeric-looking
        # fields (mobile, pincode, bank_account) as Int64; all rules expect str.
        df = df.with_columns([pl.col(c).cast(pl.Utf8, strict=False) for c in df.columns])
        logger.info("job_loaded run_id=%s rows=%d", run_id, len(df))

        store.update_run(run_id, progress_step="Starting validation rules…", progress_pct=5)
        annotated = run_pipeline(df, on_progress=_on_rule_progress, rule_ids=rule_ids)

        # Release the input frame and rule-annotated columns we no longer need.
        del df
        gc.collect()

        store.update_run(run_id, progress_step="Building exception reports", progress_pct=90)
        out_dir = settings.outputs_dir / run_id
        wide_path, long_path = build_exception_csvs(annotated, run_id, out_dir)

        del annotated
        gc.collect()

        logger.info(
            "job_complete run_id=%s wide=%s long=%s", run_id, wide_path.name, long_path.name
        )
        store.update_run(
            run_id,
            status="completed",
            finished_at=_now(),
            wide_csv=str(wide_path),
            long_csv=str(long_path),
            progress_step="Done",
            progress_pct=100,
        )
        # Log run completion
        store.log_audit_event(
            action="run_completed",
            target=run_id,
            detail=f"upload_id={upload_id}",
        )

        # Pre-generate workpaper in background (best-effort; on failure, download builds on-demand)
        try:
            _build_workpaper_background(run_id, upload)
        except Exception as exc:
            logger.warning("workpaper_prebuild_failed run_id=%s error=%s", run_id, str(exc))
    except _RunCancelled:
        _cancel_requests.discard(run_id)
        store.update_run(run_id, status="cancelled", finished_at=_now(), error="Stopped by user.")
        logger.info("job_cancelled run_id=%s", run_id)
        # Log run cancellation
        store.log_audit_event(
            action="run_cancelled",
            target=run_id,
            detail=f"upload_id={upload_id}",
        )
    except Exception as exc:
        logger.error("job_failed run_id=%s error=%s", run_id, type(exc).__name__)
        store.update_run(run_id, status="failed", finished_at=_now(), error=str(exc))
        # Log run failure
        store.log_audit_event(
            action="run_failed",
            target=run_id,
            detail=f"upload_id={upload_id}, error={type(exc).__name__}",
        )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str):
    import json

    from fcmr_core.rules.registry import CATEGORIES, list_rules

    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    donut_svg = None
    bar_svg = None
    lorenz_svg = None
    kyc_svg = None
    duplicates_svg = None
    summary = None
    ran_categories = None
    missing_summary = None
    cm_summaries = {}  # All 8 CM summary reports
    cm_unavailable = []  # CM summaries that could not run (missing data)
    rules_run = []
    sibling_runs = []

    # Determine which rules were run and build rules_run list
    try:
        selected_rules_json = run.get("selected_rules")
        if selected_rules_json:
            selected_rule_ids = json.loads(selected_rules_json)
            rules_run = [
                {"rule_id": r.rule_id, "description": r.description}
                for r in list_rules()
                if r.rule_id in selected_rule_ids
            ]
        else:
            rules_run = [{"rule_id": r.rule_id, "description": r.description} for r in list_rules()]
    except Exception:
        rules_run = []

    # Get sibling runs (other runs on the same upload)
    try:
        sibling_runs = store.list_runs(run["upload_id"])
    except Exception:
        sibling_runs = []

    # Map selected_rules to category labels
    if run.get("selected_rules"):
        try:
            selected_rules = json.loads(run["selected_rules"])
            if selected_rules:
                selected_set = set(selected_rules)
                matching_cats = []
                for cat in CATEGORIES:
                    if all(r in selected_set for r in cat["rule_ids"]):
                        matching_cats.append(cat["label"])
                if matching_cats:
                    ran_categories = ", ".join(matching_cats)
        except Exception:
            pass
    if not ran_categories:
        ran_categories = "All Categories"

    if run["status"] == "completed" and run["wide_csv"]:
        wide_path = Path(run["wide_csv"])
        if wide_path.exists():
            status_counts = aggregate_status_counts(wide_path)
            # Get ALL exception codes (not just top 10)
            all_exception_codes = aggregate_exception_codes(wide_path, top_n=None)
            # Get top 10 for the bar chart (for readability)
            top_exception_codes = aggregate_exception_codes(wide_path, top_n=10)

            donut_svg = build_donut_svg(status_counts, width=300, height=300)
            bar_svg = build_bar_chart(top_exception_codes, width=700, height=400)

            # B5 Charts: Lorenz, KYC Completeness, Duplicates Pie

            # Lorenz curve of exception concentration — sourced from the WIDE CSV,
            # which carries overall_status/exception_count (the raw upload table does
            # not have those columns, which previously made this block always fail).
            try:
                wide_df = pl.read_csv(wide_path, infer_schema_length=0)
                if "exception_count" in wide_df.columns and "overall_status" in wide_df.columns:
                    counts = (
                        wide_df.filter(pl.col("overall_status") != "OK")
                        .with_columns(
                            pl.col("exception_count").cast(pl.Int64, strict=False).fill_null(0)
                        )
                        .filter(pl.col("exception_count") > 0)
                        .sort("exception_count", descending=True)["exception_count"]
                        .to_list()
                    )
                    total_exc = sum(counts)
                    if total_exc > 0:
                        cumulative = []
                        running = 0
                        for c in counts:
                            running += c
                            cumulative.append(running / total_exc * 100)
                        lorenz_svg = build_lorenz_curve(cumulative)
            except Exception:
                pass  # Lorenz is best-effort

            # KYC Completeness: field coverage % across the raw upload dataset.
            try:
                df = store.get_upload_df(run["upload_id"])
                if df is not None and not df.is_empty():
                    field_coverage = {}
                    for field in ["pan", "aadhaar", "mobile", "email", "dob", "voter_id"]:
                        if field in df.columns:
                            present = (
                                df.filter(pl.col(field).is_not_null())
                                .filter(
                                    pl.col(field).cast(pl.Utf8, strict=False).str.len_chars() > 0
                                )
                                .height
                            )
                            coverage = (present / len(df) * 100) if len(df) > 0 else 0
                            field_coverage[field.upper()] = coverage
                    if field_coverage:
                        kyc_svg = build_kyc_completeness_bar(field_coverage)
            except Exception:
                pass  # KYC chart is best-effort

            # Duplicates pie: breakdown of duplicate exception types (from aggregates).
            duplicate_types = {
                code: n for code, n in all_exception_codes.items() if "DUPLICATE" in code
            }
            if duplicate_types:
                duplicates_svg = build_duplicates_pie(duplicate_types)

            total = sum(status_counts.values())
            all_codes = [{"exception_code": c, "count": n} for c, n in all_exception_codes.items()]
            summary = {
                "total": total,
                "status_counts": status_counts,
                "exception_codes": top_exception_codes,
                "all_codes": all_codes,
            }

            if run.get("long_csv"):
                long_path = Path(run["long_csv"])
                if long_path.exists():
                    missing_summary = aggregate_missing_data(long_path, total)

            # Compute all 8 CM summary reports (for CM runs)
            cm_unavailable = []  # Collect unavailable summaries (missing data)
            try:
                upload = store.get_upload(run["upload_id"])
                if upload and upload.get("report_type") == "customer_master":
                    df = store.get_upload_df(run["upload_id"])
                    if df is not None and not df.is_empty():
                        # Report #1: Geographic distribution
                        geo = generate_geographic_distribution(df)
                        if geo and not geo.is_empty():
                            if "note" in geo.columns:
                                cm_unavailable.append(
                                    {"title": "Geographic Distribution", "reason": geo[0, "note"]}
                                )
                            else:
                                cm_summaries["geographic"] = {
                                    "title": "Geographic Distribution",
                                    "data": geo.to_dicts(),
                                    "columns": geo.columns,
                                }
                        # Report #2: KYC completeness
                        kyc = generate_kyc_completeness(df)
                        if kyc and not kyc.is_empty():
                            if "note" in kyc.columns:
                                cm_unavailable.append(
                                    {"title": "KYC Field Completeness", "reason": kyc[0, "note"]}
                                )
                            else:
                                cm_summaries["kyc_completeness"] = {
                                    "title": "KYC Field Completeness",
                                    "data": kyc.to_dicts(),
                                    "columns": kyc.columns,
                                }
                        # Report #3: Demographics
                        demo = generate_demographic_distribution(df)
                        if demo and not demo.is_empty():
                            if "note" in demo.columns:
                                cm_unavailable.append(
                                    {"title": "Demographic Distribution", "reason": demo[0, "note"]}
                                )
                            else:
                                cm_summaries["demographics"] = {
                                    "title": "Demographic Distribution",
                                    "data": demo.to_dicts(),
                                    "columns": demo.columns,
                                }
                        # Report #4: Duplication summary
                        dup = generate_duplication_summary(df)
                        if dup and not dup.is_empty():
                            if "note" in dup.columns:
                                cm_unavailable.append(
                                    {"title": "Duplication Summary", "reason": dup[0, "note"]}
                                )
                            else:
                                cm_summaries["duplicates"] = {
                                    "title": "Duplication Summary",
                                    "data": dup.to_dicts(),
                                    "columns": dup.columns,
                                }
                        # Report #5: Co-applicant overlap
                        coapp = generate_coapplicant_overlap(df)
                        if coapp and not coapp.is_empty():
                            if "note" in coapp.columns:
                                cm_unavailable.append(
                                    {"title": "Co-Applicant Overlap", "reason": coapp[0, "note"]}
                                )
                            else:
                                cm_summaries["coapplicant"] = {
                                    "title": "Co-Applicant Overlap",
                                    "data": coapp.to_dicts(),
                                    "columns": coapp.columns,
                                }
                        # Report #6: Cluster distribution
                        cluster = generate_cluster_distribution(df)
                        if cluster and not cluster.is_empty():
                            if "note" in cluster.columns:
                                cm_unavailable.append(
                                    {
                                        "title": "Related-Party Clusters",
                                        "reason": cluster[0, "note"],
                                    }
                                )
                            else:
                                cm_summaries["clusters"] = {
                                    "title": "Related-Party Clusters",
                                    "data": cluster.to_dicts(),
                                    "columns": cluster.columns,
                                }
                        # Report #7: Data quality
                        dq = generate_data_quality_summary(df)
                        if dq and not dq.is_empty():
                            if "note" in dq.columns:
                                cm_unavailable.append(
                                    {"title": "Data Quality Summary", "reason": dq[0, "note"]}
                                )
                            else:
                                cm_summaries["data_quality"] = {
                                    "title": "Data Quality Summary",
                                    "data": dq.to_dicts(),
                                    "columns": dq.columns,
                                }
                        # Report #8: LAN concentration
                        lan = generate_lan_concentration(df)
                        if lan and not lan.is_empty():
                            if "note" in lan.columns:
                                cm_unavailable.append(
                                    {
                                        "title": "LAN Concentration (Top 10)",
                                        "reason": lan[0, "note"],
                                    }
                                )
                            else:
                                cm_summaries["lan_concentration"] = {
                                    "title": "LAN Concentration (Top 10)",
                                    "data": lan.to_dicts(),
                                    "columns": lan.columns,
                                }
                        # B4.1: Aadhaar coverage
                        aadhaar_cov = generate_aadhaar_coverage(df)
                        if aadhaar_cov and not aadhaar_cov.is_empty():
                            if "note" in aadhaar_cov.columns:
                                cm_unavailable.append(
                                    {"title": "Aadhaar Coverage", "reason": aadhaar_cov[0, "note"]}
                                )
                            else:
                                cm_summaries["aadhaar_coverage"] = {
                                    "title": "Aadhaar Coverage",
                                    "data": aadhaar_cov.to_dicts(),
                                    "columns": aadhaar_cov.columns,
                                }
                        # B4.2: Fraud-risk flags
                        fraud_flags = generate_fraud_risk_flags(df)
                        if fraud_flags and not fraud_flags.is_empty():
                            if "note" in fraud_flags.columns:
                                cm_unavailable.append(
                                    {"title": "Fraud-Risk Flags", "reason": fraud_flags[0, "note"]}
                                )
                            else:
                                cm_summaries["fraud_risk_flags"] = {
                                    "title": "Fraud-Risk Flags",
                                    "data": fraud_flags.to_dicts(),
                                    "columns": fraud_flags.columns,
                                }
                        # B4.3: Co-applicant concentration
                        coapp_conc = generate_coapplicant_concentration(df)
                        if coapp_conc and not coapp_conc.is_empty():
                            if "note" in coapp_conc.columns:
                                cm_unavailable.append(
                                    {
                                        "title": "Co-Applicant Concentration",
                                        "reason": coapp_conc[0, "note"],
                                    }
                                )
                            else:
                                cm_summaries["coapplicant_concentration"] = {
                                    "title": "Co-Applicant Concentration",
                                    "data": coapp_conc.to_dicts(),
                                    "columns": coapp_conc.columns,
                                }
                        # B4.4: Bank account anomalies
                        bank_anomalies = generate_bank_account_anomalies(df)
                        if bank_anomalies and not bank_anomalies.is_empty():
                            if "note" in bank_anomalies.columns:
                                cm_unavailable.append(
                                    {
                                        "title": "Bank Account Anomalies",
                                        "reason": bank_anomalies[0, "note"],
                                    }
                                )
                            else:
                                cm_summaries["bank_account_anomalies"] = {
                                    "title": "Bank Account Anomalies",
                                    "data": bank_anomalies.to_dicts(),
                                    "columns": bank_anomalies.columns,
                                }
            except Exception:
                cm_summaries = {}

    return templates.TemplateResponse(
        request=request,
        name="run_detail.html",
        context={
            "run": run,
            "summary": summary,
            "donut_svg": donut_svg,
            "bar_svg": bar_svg,
            "lorenz_svg": lorenz_svg,
            "kyc_svg": kyc_svg,
            "duplicates_svg": duplicates_svg,
            "ran_categories": ran_categories,
            "missing_summary": missing_summary,
            "cm_summaries": cm_summaries,
            "cm_unavailable": cm_unavailable,
            "rules_run": rules_run,
            "sibling_runs": sibling_runs,
        },
    )


@router.get("/runs/{run_id}/export/svg")
async def export_charts_svg(run_id: str, dl_token: str | None = Query(None)):
    """Export donut + bar charts as a single SVG."""
    run = store.get_run(run_id)
    if not run or run["status"] != "completed" or not run["wide_csv"]:
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    wide_path = Path(run["wide_csv"])
    if not wide_path.exists():
        raise HTTPException(status_code=404, detail="Wide CSV not found")

    status_counts = aggregate_status_counts(wide_path)
    exception_codes = aggregate_exception_codes(wide_path, top_n=10)

    donut_svg = build_donut_svg(status_counts, width=300, height=300)
    bar_svg = build_bar_chart(exception_codes, width=700, height=400)

    combined_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 1000 900" xmlns="http://www.w3.org/2000/svg">
  <style>
    .title {{ font-size: 18px; font-weight: bold; fill: #1f2937; }}
  </style>
  <text x="20" y="30" class="title">Analytics Summary</text>

  <!-- Donut chart -->
  <g transform="translate(20, 60)">
    {donut_svg}
  </g>

  <!-- Bar chart -->
  <g transform="translate(20, 450)">
    {bar_svg}
  </g>
</svg>"""

    headers = {}
    if dl_token:
        headers["Set-Cookie"] = f"dl_done_{dl_token}=1; Path=/; Max-Age=10"

    return Response(combined_svg, media_type="image/svg+xml", headers=headers)


@router.get("/runs/{run_id}/charts/donut.svg")
async def get_donut_chart(run_id: str):
    """Get donut chart SVG for embedding."""
    run = store.get_run(run_id)
    if not run or run["status"] != "completed" or not run["wide_csv"]:
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    wide_path = Path(run["wide_csv"])
    if not wide_path.exists():
        raise HTTPException(status_code=404, detail="Wide CSV not found")

    status_counts = aggregate_status_counts(wide_path)
    donut_svg = build_donut_svg(status_counts, width=300, height=300)

    return {"donut_svg": donut_svg}


@router.get("/runs/{run_id}/charts/bar.svg")
async def get_bar_chart(run_id: str):
    """Get bar chart SVG for embedding."""
    run = store.get_run(run_id)
    if not run or run["status"] != "completed" or not run["wide_csv"]:
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    wide_path = Path(run["wide_csv"])
    if not wide_path.exists():
        raise HTTPException(status_code=404, detail="Wide CSV not found")

    exception_codes = aggregate_exception_codes(wide_path, top_n=10)
    bar_svg = build_bar_chart(exception_codes, width=700, height=400)

    return {"bar_svg": bar_svg}


@router.get("/runs/{run_id}/export/workpaper")
async def export_workpaper(run_id: str, dl_token: str | None = Query(None)):
    """Generate and download workpaper Excel."""
    run = store.get_run(run_id)
    if not run or run["status"] != "completed" or not run["wide_csv"] or not run["long_csv"]:
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    # Lookup engagement; use "default" as fallback if missing or not found
    engagement_id = run.get("engagement_id") or "default"
    engagement = store.get_engagement(engagement_id)
    if not engagement:
        # Create a minimal engagement object if not found
        engagement = {
            "engagement_id": engagement_id,
            "name": "Audit Engagement",
            "client_name": "—",
            "period_from": None,
            "period_to": None,
        }

    wide_path = Path(run["wide_csv"])
    long_path = Path(run["long_csv"])
    if not wide_path.exists() or not long_path.exists():
        raise HTTPException(status_code=404, detail="CSV files not found")

    # Fetch upload for workpaper metadata
    upload = store.get_upload(run["upload_id"])
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Serve cached workpaper if present on disk
    if run.get("workpaper_path"):
        cached_path = Path(run["workpaper_path"])
        if cached_path.exists():
            headers = {}
            if dl_token:
                headers["Set-Cookie"] = f"dl_done_{dl_token}=1; Path=/; Max-Age=10"
            return FileResponse(
                cached_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=cached_path.name,
                headers=headers,
            )

    try:
        df = pl.read_csv(wide_path, infer_schema_length=0)
        population = len(df)
        exception_count = df.get_column("overall_status").ne("OK").sum()

        # Use resolved engagement_id (fallback to "default" if missing)
        resolved_engagement_id = engagement_id or "default"
        sample_records = select_sample(
            wide_path,
            engagement_id=resolved_engagement_id,
            run_id=run_id,
            population=population,
            exception_count=exception_count,
        )

        workpaper_path = build_workpaper(
            engagement=engagement,
            run=run,
            upload=upload,
            wide_csv_path=wide_path,
            long_csv_path=long_path,
            sample_records=sample_records,
            output_dir=settings.outputs_dir / run_id,
        )

        store.update_run(run_id, workpaper_path=str(workpaper_path))

        headers = {}
        if dl_token:
            headers["Set-Cookie"] = f"dl_done_{dl_token}=1; Path=/; Max-Age=10"

        return FileResponse(
            workpaper_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=workpaper_path.name,
            headers=headers,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workpaper generation failed: {exc}") from exc


@router.get("/runs/{run_id}/results.json")
async def get_run_results_json(run_id: str):
    """Get run results as JSON (read-only API)."""
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "completed" or not run["wide_csv"]:
        raise HTTPException(status_code=400, detail="Run not completed yet")

    wide_path = Path(run["wide_csv"])
    if not wide_path.exists():
        raise HTTPException(status_code=404, detail="Wide CSV not found")

    # Get status counts and top exception codes
    status_counts = aggregate_status_counts(wide_path)
    exception_codes = aggregate_exception_codes(wide_path, top_n=10)

    return {
        "run_id": run_id,
        "status": run["status"],
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "status_counts": status_counts,
        "top_exception_codes": exception_codes,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
