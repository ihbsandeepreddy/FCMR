"""Data Consolidation — merge multiple uploads of the same report type."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from fcmr_core.catalog import store

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

_REPORT_LABELS = {
    "customer_master": "Customer Master",
    "ead_files": "EAD Files",
    "collection_report": "Collection Report",
    "disbursement_report": "Disbursement Report",
    "technical_writeoff": "Technical Write-Off",
}


def _label(report_type: str) -> str:
    return _REPORT_LABELS.get(report_type, report_type.replace("_", " ").title())


def _build_df(engagement_id: str | None, report_type: str) -> pl.DataFrame:
    """Load all ready uploads of the given type, rename to canonical, stack."""
    uploads = store.list_uploads(engagement_id=engagement_id)
    ready = [u for u in uploads if u["report_type"] == report_type and u["status"] == "ready"]
    if not ready:
        return pl.DataFrame()

    frames: list[pl.DataFrame] = []
    for upload in ready:
        df = store.get_upload_df(upload["upload_id"])
        mapping: dict[str, str] = json.loads(upload.get("column_mapping") or "{}")
        rename = {raw: canonical for raw, canonical in mapping.items() if raw in df.columns}
        if rename:
            df = df.rename(rename)
        df = df.with_columns(pl.lit(upload["filename"]).alias("_source_file"))
        frames.append(df)

    return pl.concat(frames, how="diagonal_relaxed")


# ── Hub ──────────────────────────────────────────────────────────────────────

@router.get("/consolidate", response_class=HTMLResponse)
async def consolidate_hub(request: Request):
    engagement_id = request.session.get("engagement_id")
    all_uploads = store.list_uploads(engagement_id=engagement_id)

    # Group by report_type — only types with ≥1 ready upload
    from collections import defaultdict
    groups: dict[str, dict] = defaultdict(lambda: {"ready": 0, "pending": 0, "total_rows": 0})
    for u in all_uploads:
        rt = u["report_type"] or "unknown"
        if u["status"] == "ready":
            groups[rt]["ready"] += 1
            groups[rt]["total_rows"] += u.get("row_count") or 0
        elif u["status"] == "mapping_pending":
            groups[rt]["pending"] += 1

    report_types = [
        {
            "report_type": rt,
            "label": _label(rt),
            "ready": info["ready"],
            "pending": info["pending"],
            "total_rows": info["total_rows"],
        }
        for rt, info in sorted(groups.items())
        if info["ready"] > 0
    ]

    return templates.TemplateResponse(
        request=request,
        name="consolidate_hub.html",
        context={"report_types": report_types},
    )


# ── Detail / preview ─────────────────────────────────────────────────────────

@router.get("/consolidate/{report_type}", response_class=HTMLResponse)
async def consolidate_detail(request: Request, report_type: str):
    engagement_id = request.session.get("engagement_id")
    all_uploads = store.list_uploads(engagement_id=engagement_id)
    ready_uploads = [
        u for u in all_uploads if u["report_type"] == report_type and u["status"] == "ready"
    ]
    if not ready_uploads:
        raise HTTPException(status_code=404, detail=f"No ready uploads for {report_type}")

    df = _build_df(engagement_id, report_type)

    total_rows = len(df)
    total_cols = len(df.columns)
    source_files = (
        df["_source_file"].unique().sort().to_list() if "_source_file" in df.columns else []
    )

    # Preview: first 100 rows, cast all to string for safe display
    preview_df = df.head(100).with_columns(
        [pl.col(c).cast(pl.Utf8, strict=False) for c in df.columns]
    )
    preview_cols = preview_df.columns
    preview_rows = preview_df.rows()

    return templates.TemplateResponse(
        request=request,
        name="consolidate_detail.html",
        context={
            "report_type": report_type,
            "label": _label(report_type),
            "total_rows": total_rows,
            "total_cols": total_cols,
            "file_count": len(ready_uploads),
            "source_files": source_files,
            "preview_cols": preview_cols,
            "preview_rows": preview_rows,
            "preview_count": len(preview_rows),
        },
    )


# ── Downloads ────────────────────────────────────────────────────────────────

@router.get("/consolidate/{report_type}/download/csv")
async def consolidate_csv(request: Request, report_type: str):
    engagement_id = request.session.get("engagement_id")
    df = _build_df(engagement_id, report_type)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data to consolidate.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{_label(report_type).replace(' ', '_')}_{ts}.csv"
    csv_bytes = df.write_csv().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/consolidate/{report_type}/download/excel")
async def consolidate_excel(request: Request, report_type: str):
    engagement_id = request.session.get("engagement_id")
    df = _build_df(engagement_id, report_type)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data to consolidate.")

    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _label(report_type)[:31]

    hdr_fill = PatternFill(start_color="5C3D1E", end_color="5C3D1E", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    data_font = Font(size=10)

    cols = df.columns
    for ci, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=ci, value=col.replace("_", " ").title())
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    rows_data = df.with_columns(
        [pl.col(c).cast(pl.Utf8, strict=False) for c in cols]
    ).rows()
    for ri, row in enumerate(rows_data, 2):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=val if val != "None" else None)
            cell.font = data_font

    for ci, col in enumerate(cols, 1):
        sample = df[col].drop_nulls().head(200).cast(pl.Utf8, strict=False)
        max_len = max(len(col), 10)
        if sample.len() > 0:
            max_len = max(max_len, sample.map_elements(len, return_dtype=pl.Int32).max() or 0)
        ws.column_dimensions[get_column_letter(ci)].width = min(max_len + 2, 40)

    ws.freeze_panes = "A2"

    # Summary sheet
    ws2 = wb.create_sheet("Summary")
    label = _label(report_type)
    ws2["A1"] = f"{label} — Consolidation Summary"
    ws2["A1"].font = Font(bold=True, size=12)
    ws2["A3"] = "Report Type"
    ws2["B3"] = label
    ws2["A4"] = "Total Rows"
    ws2["B4"] = len(df)
    ws2["A5"] = "Total Columns"
    ws2["B5"] = len(cols)
    ws2["A6"] = "Generated At"
    ws2["B6"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if "_source_file" in df.columns:
        ws2["A8"] = "Source Files"
        ws2["A8"].font = Font(bold=True)
        source_files = df["_source_file"].unique().sort().to_list()
        for i, fname in enumerate(source_files):
            ws2.cell(row=9 + i, column=1, value=fname)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{label.replace(' ', '_')}_{ts}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
