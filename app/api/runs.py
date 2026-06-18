"""Run (analytics execution) endpoints."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.catalog import store
from fcmr_core.config import settings
from fcmr_core.ingestion.pipeline import read_parquet
from fcmr_core.reporting.builder import build_exception_csvs
from fcmr_core.reporting.aggregation import aggregate_status_counts, aggregate_exception_codes
from fcmr_core.reporting.charts import build_donut_svg, build_bar_chart
from fcmr_core.reporting.workpaper import build_workpaper
from fcmr_core.sampling.sample import select_sample
from fcmr_core.rules.registry import run_pipeline

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.post("/uploads/{upload_id}/run")
async def start_run(upload_id: str, background_tasks: BackgroundTasks):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "ready":
        raise HTTPException(status_code=400, detail="Upload is not ready")

    parquet_path = Path(upload["parquet_path"])
    if not parquet_path.exists():
        raise HTTPException(status_code=500, detail="Parquet file not found on disk")

    run_id = store.create_run(upload_id)
    store.update_run(run_id, status="running", started_at=_now())

    # Run in a background thread so the browser gets an immediate response.
    # FastAPI BackgroundTasks run after the response is sent but in the same
    # process thread pool — sufficient for CPU-bound work without a job queue.
    background_tasks.add_task(_run_analytics, run_id, parquet_path)

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


def _run_analytics(run_id: str, parquet_path: Path) -> None:
    """Execute the full analytics pipeline and update the catalog when done."""
    try:
        df = read_parquet(parquet_path).collect()
        annotated = run_pipeline(df)
        out_dir = settings.outputs_dir / run_id
        wide_path, long_path = build_exception_csvs(annotated, run_id, out_dir)
        store.update_run(
            run_id,
            status="completed",
            finished_at=_now(),
            wide_csv=str(wide_path),
            long_csv=str(long_path),
        )
    except Exception as exc:
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
            # Aggregate status counts and exception codes
            status_counts = aggregate_status_counts(wide_path)
            exception_codes = aggregate_exception_codes(wide_path, top_n=10)

            # Generate SVG charts
            donut_svg = build_donut_svg(status_counts, width=300, height=300)
            bar_svg = build_bar_chart(exception_codes, width=700, height=400)

            total = sum(status_counts.values())
            summary = {
                "total": total,
                "status_counts": status_counts,
                "exception_codes": exception_codes,
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


def _top_exception_codes(long_csv_path: str | None, n: int = 10):
    if not long_csv_path:
        return []
    p = Path(long_csv_path)
    if not p.exists():
        return []
    df = pl.read_csv(str(p))
    if df.is_empty() or "exception_code" not in df.columns:
        return []
    return (
        df["exception_code"]
        .value_counts()
        .sort("count", descending=True)
        .head(n)
        .iter_rows(named=True)
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

    # Generate charts
    status_counts = aggregate_status_counts(wide_path)
    exception_codes = aggregate_exception_codes(wide_path, top_n=10)

    donut_svg = build_donut_svg(status_counts, width=300, height=300)
    bar_svg = build_bar_chart(exception_codes, width=700, height=400)

    # Combine into a single SVG
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
        # Calculate sample size and select sample
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

        # Build workpaper
        workpaper_path = build_workpaper(
            engagement=engagement,
            run=run,
            wide_csv_path=wide_path,
            sample_records=sample_records,
            output_dir=settings.outputs_dir / run_id,
        )

        # Update run record with workpaper path
        store.update_run(run_id, workpaper_path=str(workpaper_path))

        # Return the file
        return FileResponse(
            workpaper_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=workpaper_path.name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workpaper generation failed: {exc}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
