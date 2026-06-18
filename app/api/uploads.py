"""Upload, column-mapping, and ingest endpoints + main dashboard UI."""

from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.catalog import store
from fcmr_core.config import settings
from fcmr_core.ingestion.pipeline import ingest_csv, sniff_headers
from fcmr_core.schemas.loader import available_report_types, get_canonical_fields, get_schema


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Scope uploads to active engagement
    engagement_id = request.session.get("engagement_id")
    uploads = store.list_uploads(engagement_id=engagement_id) if engagement_id else []
    report_types = available_report_types()
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"uploads": uploads, "report_types": report_types},
    )


# ---------------------------------------------------------------------------
# Phase 1 — upload the file and redirect to column-mapping page
# ---------------------------------------------------------------------------

@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    report_types = available_report_types()
    return templates.TemplateResponse(
        request=request, name="upload.html",
        context={"report_types": report_types},
    )


@router.post("/upload")
async def do_upload(
    request: Request,
    report_type: str = Form(...),
    folder: list[UploadFile] = File(default=[]),
    files: list[UploadFile] = File(default=[]),
):
    import zipfile
    import tempfile

    # Get engagement_id from session
    engagement_id = request.session.get("engagement_id")

    # Collect all files to process
    upload_files = folder if folder else files
    if not upload_files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Generate one batch_id for this upload request
    batch_id = str(uuid.uuid4())
    ingestion_time = _now()

    # Process files from .zip if present
    temp_dir = None
    try:
        processed_files = []

        for file in upload_files:
            if file.filename and file.filename.lower().endswith(".zip"):
                # Unzip and extract CSVs
                content = await file.read()
                temp_dir = tempfile.TemporaryDirectory()
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    zf.extractall(temp_dir.name)
                # Collect all CSVs from unzipped directory
                for root, dirs, filenames in os.walk(temp_dir.name):
                    for fname in filenames:
                        if fname.lower().endswith(".csv"):
                            full_path = Path(root) / fname
                            processed_files.append((fname, full_path.read_bytes()))
            elif file.filename and file.filename.lower().endswith(".csv"):
                # Regular CSV file
                content = await file.read()
                processed_files.append((file.filename, content))

        if not processed_files:
            raise HTTPException(status_code=400, detail="No CSV files found.")

        # Create upload row for each file
        created_uploads = []
        for filename, content in processed_files:
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail=f"File {filename} exceeds 2 GB limit.")

            # Create upload row with batch_id and engagement_id
            upload_id = store.create_upload(
                report_type,
                filename,
                batch_id=batch_id,
                engagement_id=engagement_id,
            )

            # Store CSV to disk
            dest_dir = settings.uploads_dir / upload_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            csv_path = dest_dir / filename
            csv_path.write_bytes(content)

            # Sniff headers and set mapping_pending
            headers = sniff_headers(csv_path)
            store.set_mapping_pending(upload_id, csv_path=csv_path, sniffed_headers=headers)

            created_uploads.append((upload_id, filename))

        # Redirect to dashboard (or could show a batch summary page)
        return RedirectResponse(url="/dashboard", status_code=303)

    finally:
        if temp_dir:
            temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Phase 2 — column-mapping UI
# ---------------------------------------------------------------------------

@router.get("/uploads/{upload_id}/map-columns", response_class=HTMLResponse)
async def map_columns_form(request: Request, upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "mapping_pending":
        return RedirectResponse(url=f"/uploads/{upload_id}", status_code=303)

    raw_headers: list[str] = json.loads(upload["sniffed_headers"] or "[]")
    schema = get_schema(upload["report_type"])

    suggested: dict[str, str] = schema.map_headers(raw_headers) if schema else {}
    canonical_fields = get_canonical_fields(upload["report_type"])

    return templates.TemplateResponse(
        request=request, name="column_map.html",
        context={
            "upload": upload,
            "raw_headers": raw_headers,
            "suggested": suggested,
            "canonical_fields": canonical_fields,
        },
    )


@router.post("/uploads/{upload_id}/map-columns")
async def do_map_columns(request: Request, upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    form = await request.form()
    raw_headers: list[str] = json.loads(upload["sniffed_headers"] or "[]")

    # Form fields are named map_0, map_1, … matching raw_headers[i]
    user_mapping: dict[str, str] = {}
    for i, header in enumerate(raw_headers):
        canonical = str(form.get(f"map_{i}", "") or "").strip()
        if canonical and canonical != "__skip__":
            user_mapping[header] = canonical

    csv_path = Path(upload["csv_path"] or "")
    if not csv_path.exists():
        raise HTTPException(status_code=500, detail="Uploaded CSV file not found on disk.")

    try:
        result = ingest_csv(csv_path, upload["report_type"], upload_id, user_mapping=user_mapping)
        store.set_upload_ready(
            upload_id,
            parquet_path=result.parquet_path,
            row_count=result.total_rows,
            column_mapping=user_mapping,
        )
    except Exception as exc:
        store.set_upload_failed(upload_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return RedirectResponse(url=f"/uploads/{upload_id}", status_code=303)


# ---------------------------------------------------------------------------
# Upload detail
# ---------------------------------------------------------------------------

@router.get("/uploads/{upload_id}", response_class=HTMLResponse)
async def upload_detail(request: Request, upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    mapping_display: list[tuple[str, str]] = []
    if upload.get("column_mapping"):
        mapping_display = list(json.loads(upload["column_mapping"]).items())

    runs = store.list_runs(upload_id)
    return templates.TemplateResponse(
        request=request, name="upload_detail.html",
        context={"upload": upload, "runs": runs, "mapping_display": mapping_display},
    )
