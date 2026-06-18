"""Run (analytics execution) endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.catalog import store
from fcmr_core.config import settings
from fcmr_core.ingestion.pipeline import read_parquet
from fcmr_core.logging_setup import get_logger
from fcmr_core.reporting.aggregation import aggregate_exception_codes, aggregate_status_counts
from fcmr_core.reporting.builder import build_exception_csvs
from fcmr_core.reporting.charts import build_bar_chart, build_donut_svg
from fcmr_core.reporting.workpaper import build_workpaper
from fcmr_core.rules.registry import run_pipeline
from fcmr_core.sampling.sample import select_sample

logger = get_logger("processing")

router = APIRouter()

# In-memory set of run IDs that have been requested to cancel.
# Checked between pipeline steps in _run_analytics.
_cancel_requests: set[str] = set()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.post("/uploads/{upload_id}/run")
async def start_run(upload_id: str, background_tasks: BackgroundTasks):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "ready":
        raise HTTPException(status_code=400, detail="Upload is not ready")

    run_id = store.create_run(upload_id)
    store.update_run(run_id, status="running", started_at=_now())

    background_tasks.add_task(_run_analytics, run_id, upload_id)

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
    return JSONResponse({
        "status": run["status"],
        "progress_step": run.get("progress_step") or "",
        "error": run.get("error") or "",
    })


def _run_analytics(run_id: str, upload_id: str) -> None:
    """Execute the full analytics pipeline and update the catalog when done."""
    def _step(label: str) -> bool:
        """Update progress step. Returns True if cancelled."""
        if run_id in _cancel_requests:
            _cancel_requests.discard(run_id)
            store.update_run(run_id, status="cancelled", finished_at=_now(),
                             error="Stopped by user.")
            logger.info("job_cancelled run_id=%s", run_id)
            return True
        store.update_run(run_id, progress_step=label)
        return False

    try:
        upload = store.get_upload(upload_id)
        logger.info("job_start run_id=%s upload_id=%s", run_id, upload_id)

        if _step("Loading data file"): return
        # Data is stored in DuckDB after ingestion (parquet is deleted post-import).
        # Fall back to reading from parquet path only if the DuckDB table is missing.
        try:
            df = store.get_upload_df(upload_id)
        except Exception:
            parquet_path = Path(upload["parquet_path"])
            if not parquet_path.exists():
                raise FileNotFoundError(
                    f"Data file not found at {parquet_path}. "
                    "Please re-upload the CSV file."
                )
            df = read_parquet(parquet_path).collect()

        # Cast every column to string. DuckDB infers numeric-looking fields
        # (mobile, pincode, bank_account) as Int64; all rules expect str values.
        df = df.with_columns([
            pl.col(c).cast(pl.Utf8, strict=False) for c in df.columns
        ])
        logger.info("job_loaded run_id=%s rows=%d", run_id, len(df))

        if _step("Running 27 validation rules"): return
        annotated = run_pipeline(df)

        if _step("Building exception reports"): return
        out_dir = settings.outputs_dir / run_id
        wide_path, long_path = build_exception_csvs(annotated, run_id, out_dir)

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
        )
    except Exception as exc:
        logger.error("job_failed run_id=%s error=%s", run_id, type(exc).__name__)
        store.update_run(run_id, status="failed", finished_at=_now(), error=str(exc))


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    donut_svg = None
    bar_svg = None
    summary = None

    if run["status"] == "completed" and run["wide_csv"]:
        wide_path = Path(run["wide_csv"])
        if wide_path.exists():
            status_counts = aggregate_status_counts(wide_path)
            exception_codes = aggregate_exception_codes(wide_path, top_n=10)

            donut_svg = build_donut_svg(status_counts, width=300, height=300)
            bar_svg = build_bar_chart(exception_codes, width=700, height=400)

            total = sum(status_counts.values())
            top_codes = [{"exception_code": c, "count": n} for c, n in exception_codes.items()]
            summary = {
                "total": total,
                "status_counts": status_counts,
                "exception_codes": exception_codes,
                "top_codes": top_codes,
            }

    return templates.TemplateResponse(
        request=request, name="run_detail.html",
        context={
            "run": run,
            "summary": summary,
            "donut_svg": donut_svg,
            "bar_svg": bar_svg,
        },
    )


@router.get("/runs/{run_id}/export/svg")
async def export_charts_svg(run_id: str):
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

    return combined_svg


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
async def export_workpaper(run_id: str):
    """Generate and download workpaper Excel."""
    run = store.get_run(run_id)
    if not run or run["status"] != "completed" or not run["wide_csv"] or not run["long_csv"]:
        raise HTTPException(status_code=404, detail="Run not found or not completed")

    engagement = store.get_engagement(run["engagement_id"])
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    wide_path = Path(run["wide_csv"])
    long_path = Path(run["long_csv"])
    if not wide_path.exists() or not long_path.exists():
        raise HTTPException(status_code=404, detail="CSV files not found")

    try:
        df = pl.read_csv(wide_path)
        population = len(df)
        exception_count = sum(1 for val in df["overall_status"] if val != "OK")

        sample_records = select_sample(
            wide_path,
            engagement_id=run["engagement_id"],
            run_id=run_id,
            population=population,
            exception_count=exception_count,
        )

        workpaper_path = build_workpaper(
            engagement=engagement,
            run=run,
            wide_csv_path=wide_path,
            sample_records=sample_records,
            output_dir=settings.outputs_dir / run_id,
        )

        store.update_run(run_id, workpaper_path=str(workpaper_path))

        return FileResponse(
            workpaper_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=workpaper_path.name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workpaper generation failed: {exc}") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat()
