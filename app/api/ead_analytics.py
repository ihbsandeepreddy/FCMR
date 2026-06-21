"""EAD Analytics — trigger, track, and display EAD portfolio analytics runs."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.analytics.ead_analytics import (
    _REPORT_FUNCTIONS,
    _REPORT_SHEET_NAMES,
    compute_summary_stats,
    run_ead_analytics,
)
from fcmr_core.analytics.ead_summary import (
    generate_collateral_coverage,
    generate_data_quality_summary_ead,
    generate_dpd_risk_distribution,
    generate_portfolio_concentration,
    generate_provision_coverage,
    generate_sanction_disbursement_variance,
    generate_stage_distribution,
    generate_writeoff_recovery,
)
from fcmr_core.catalog import store
from fcmr_core.config import settings

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Shared: build merged EAD DataFrame (same as ead_consolidate)
# ---------------------------------------------------------------------------


def _build_ead_df(engagement_id: str | None) -> pl.DataFrame:
    uploads = store.list_uploads(engagement_id=engagement_id)
    ead_ready = [u for u in uploads if u["report_type"] == "ead_files" and u["status"] == "ready"]
    if not ead_ready:
        return pl.DataFrame()

    frames: list[pl.DataFrame] = []
    for upload in ead_ready:
        df = store.get_upload_df(upload["upload_id"])
        mapping: dict[str, str] = json.loads(upload.get("column_mapping") or "{}")
        rename = {raw: canonical for raw, canonical in mapping.items() if raw in df.columns}
        if rename:
            df = df.rename(rename)
        df = df.with_columns(pl.lit(upload["filename"]).alias("_source_file"))
        frames.append(df)

    return pl.concat(frames, how="diagonal_relaxed")


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


def _run_ead_background(
    run_id: str,
    engagement_id: str,
    report_keys: list[str] | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
) -> None:
    output_dir = settings.outputs_dir / f"ead_{run_id}"

    def _on_progress(completed: int, total: int, label: str) -> None:
        pct = int(completed / total * 100) if total > 0 else 0
        store.update_ead_run(run_id, progress_step=label, progress_pct=pct)

    try:
        store.update_ead_run(run_id, status="running", started_at=_now())
        df = _build_ead_df(engagement_id)
        if df.is_empty():
            store.update_ead_run(
                run_id,
                status="failed",
                error="No ready EAD uploads found for this engagement.",
                finished_at=_now(),
            )
            return

        run_ead_analytics(
            df,
            output_dir,
            report_keys=report_keys,
            period_from=period_from,
            period_to=period_to,
            on_progress=_on_progress,
        )
        store.update_ead_run(
            run_id,
            status="completed",
            output_dir=str(output_dir),
            finished_at=_now(),
            progress_pct=100,
            progress_step="Complete",
        )
    except Exception as exc:  # noqa: BLE001
        store.update_ead_run(
            run_id,
            status="failed",
            error=str(exc),
            finished_at=_now(),
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/ead/analyze")
async def trigger_ead_analytics(request: Request, background_tasks: BackgroundTasks):
    engagement_id = request.session.get("engagement_id")
    if not engagement_id:
        raise HTTPException(status_code=400, detail="No active engagement selected.")

    form = await request.form()
    selected = form.getlist("selected_reports")
    valid_keys = {k for k, _, _ in _REPORT_FUNCTIONS}
    report_keys: list[str] | None = [k for k in selected if k in valid_keys] or None

    # Read engagement period for disbursement analytics
    period_from: str | None = None
    period_to: str | None = None
    engagement = store.get_engagement(engagement_id)
    if engagement:
        period_from = engagement.get("period_from")
        period_to = engagement.get("period_to")

    run_id = store.create_ead_run(engagement_id)
    if report_keys:
        store.update_ead_run(run_id, selected_reports=json.dumps(report_keys))

    background_tasks.add_task(
        _run_ead_background,
        run_id,
        engagement_id,
        report_keys,
        period_from,
        period_to,
    )
    return RedirectResponse(url=f"/ead/runs/{run_id}", status_code=303)


@router.get("/ead/runs/{run_id}/status")
async def ead_run_status(run_id: str):
    run = store.get_ead_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="EAD run not found")
    return JSONResponse(
        {
            "status": run["status"],
            "progress_step": run.get("progress_step") or "",
            "progress_pct": run.get("progress_pct") or 0,
            "error": run.get("error") or "",
        }
    )


@router.get("/ead/runs/{run_id}", response_class=HTMLResponse)
async def ead_run_detail(request: Request, run_id: str):
    run = store.get_ead_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="EAD run not found")

    context: dict = {
        "run": run,
        "tab_list": list(_REPORT_SHEET_NAMES),
        "report_keys": [k for k, _ in _REPORT_SHEET_NAMES],
    }

    if run["status"] == "completed" and run.get("output_dir"):
        output_dir = Path(run["output_dir"])
        previews: dict[str, dict] = {}
        for key, sheet_name in _REPORT_SHEET_NAMES:
            csv_path = output_dir / f"{key}.csv"
            if csv_path.exists():
                try:
                    df = pl.read_csv(str(csv_path), infer_schema_length=0)
                    preview_df = df.head(50).with_columns(
                        [pl.col(c).cast(pl.Utf8, strict=False) for c in df.columns]
                    )
                    previews[key] = {
                        "label": sheet_name,
                        "cols": preview_df.columns,
                        "rows": preview_df.rows(),
                        "total_rows": len(df),
                    }
                except Exception:
                    previews[key] = {"label": sheet_name, "cols": [], "rows": [], "total_rows": 0}
            else:
                previews[key] = {
                    "label": sheet_name,
                    "cols": [],
                    "rows": [],
                    "total_rows": 0,
                    "missing": True,
                }

        context["previews"] = previews

        # Summary stats from merged DataFrame (re-build for stat cards)
        ead_summaries = {}
        ead_unavailable = []  # Collect unavailable summaries (missing data)
        try:
            engagement_id = run.get("engagement_id") or request.session.get("engagement_id")
            df_all = _build_ead_df(engagement_id)
            context["summary"] = compute_summary_stats(df_all)

            # Compute all 8 EAD summary reports
            if df_all is not None and not df_all.is_empty():
                summaries = [
                    ("Portfolio Concentration", generate_portfolio_concentration(df_all)),
                    ("Stage Distribution", generate_stage_distribution(df_all)),
                    ("DPD/Risk Distribution", generate_dpd_risk_distribution(df_all)),
                    ("Collateral Coverage", generate_collateral_coverage(df_all)),
                    ("Provision Coverage", generate_provision_coverage(df_all)),
                    ("Write-off & Recovery", generate_writeoff_recovery(df_all)),
                    ("Sanction vs Disbursement", generate_sanction_disbursement_variance(df_all)),
                    ("Data Quality Summary", generate_data_quality_summary_ead(df_all)),
                ]
                for title, summary_df in summaries:
                    if summary_df and not summary_df.is_empty():
                        if "note" in summary_df.columns:
                            ead_unavailable.append(
                                {"title": title, "reason": summary_df[0, "note"]}
                            )
                        else:
                            ead_summaries[title] = {
                                "title": title,
                                "data": summary_df.to_dicts(),
                                "columns": summary_df.columns,
                            }
        except Exception:
            context["summary"] = {}

        context["ead_summaries"] = ead_summaries
        context["ead_unavailable"] = ead_unavailable

        context["workpaper_available"] = (output_dir / "ead_workpaper.xlsx").exists()

    return templates.TemplateResponse(request=request, name="ead_run_detail.html", context=context)


@router.get("/ead/runs/{run_id}/download/{report}")
async def ead_download_report(run_id: str, report: str):
    run = store.get_ead_run(run_id)
    if not run or run["status"] != "completed" or not run.get("output_dir"):
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    output_dir = Path(run["output_dir"])

    if report == "workpaper":
        path = output_dir / "ead_workpaper.xlsx"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Workpaper not found")
        with path.open("rb") as f:
            data = f.read()
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="EAD_Analytics_{run_id[:8]}.xlsx"'
            },
        )

    csv_path = output_dir / f"{report}.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Report '{report}' not found")

    with csv_path.open("rb") as f:
        data = f.read()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="EAD_{report}_{ts}.csv"'},
    )
