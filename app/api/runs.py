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
from fcmr_core.logging_setup import get_logger
from fcmr_core.reporting.builder import build_exception_csvs
from fcmr_core.reporting.aggregation import aggregate_status_counts, aggregate_exception_codes
from fcmr_core.reporting.charts import build_donut_svg, build_bar_chart
from fcmr_core.reporting.workpaper import build_workpaper
from fcmr_core.sampling.sample import select_sample
from fcmr_core.rules.registry import run_pipeline

logger = get_logger("processing")

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

    run_id = store.create_run(upload_id)
    store.update_run(run_id, status="running", started_at=_now())

    background_tasks.add_task(_run_analytics, run_id, upload_id)

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

