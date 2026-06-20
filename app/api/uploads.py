"""Upload, column-mapping, and ingest endpoints + main dashboard UI."""

from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.catalog import store
from fcmr_core.config import settings
from fcmr_core.ingestion.pipeline import ingest_csv, sniff_headers
from fcmr_core.schemas.loader import available_report_types, get_canonical_fields, get_schema


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
        request=request,
        name="index.html",
        context={"uploads": uploads, "report_types": report_types},
    )


# ---------------------------------------------------------------------------
# Phase 1 — upload the file and redirect to column-mapping page
# ---------------------------------------------------------------------------


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    report_types = available_report_types()
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={"report_types": report_types},
    )


def _write_chunked(content: bytes, dest: Path) -> None:
    """Stream-write bytes in 256 KB chunks — avoids holding the file twice in RAM."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    chunk_size = 256 * 1024
    with dest.open("wb") as out:
        for i in range(0, len(content), chunk_size):
            out.write(content[i : i + chunk_size])


def _finalize_consolidated_upload(
    *,
    report_type: str,
    engagement_id: str | None,
    batch_id: str,
    ordered_groups: list,
    alignment: dict,
    unified_cols: list[str],
    source_names: list[str],
) -> str:
    """Build the combined CSV and register it as one consolidated, mapping-pending upload."""
    from fcmr_core.ingestion.consolidation import build_combined_csv

    upload_id = store.create_upload(
        report_type,
        f"{report_type}_consolidated_{len(source_names)}files.csv",
        batch_id=batch_id,
        engagement_id=engagement_id,
    )
    combined_path = settings.uploads_dir / upload_id / "consolidated.csv"
    build_combined_csv(ordered_groups, alignment, unified_cols, combined_path)
    store.set_mapping_pending(upload_id, csv_path=combined_path, sniffed_headers=unified_cols)
    store.set_upload_consolidated_meta(
        upload_id, source_count=len(source_names), source_files=source_names
    )
    return upload_id


@router.post("/upload")
async def do_upload(
    request: Request,
    report_type: str = Form(...),
    consolidate: str = Form("off"),
    folder: list[UploadFile] = File(default=[]),
    files: list[UploadFile] = File(default=[]),
):
    import shutil
    import tempfile
    import zipfile

    from fcmr_core.ingestion.consolidation import (
        FileEntry,
        group_files_by_signature,
        suggest_alignment,
        unified_columns,
    )

    # Get engagement_id from session
    engagement_id = request.session.get("engagement_id")
    consolidate_on = consolidate not in ("", "off", "false", "0", None)

    # Filter out empty UploadFile stubs that browsers send for unselected inputs
    folder = [f for f in folder if f.filename]
    files = [f for f in files if f.filename]

    # Collect all files to process
    upload_files = folder if folder else files
    if not upload_files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Generate one batch_id for this upload request
    batch_id = str(uuid.uuid4())

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

        for filename, content in processed_files:
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail=f"File {filename} exceeds 2 GB limit.")

        # ── Single file, or consolidation disabled: one upload per file (legacy) ──
        if len(processed_files) == 1 or not consolidate_on:
            for filename, content in processed_files:
                upload_id = store.create_upload(
                    report_type, filename, batch_id=batch_id, engagement_id=engagement_id
                )
                csv_path = settings.uploads_dir / upload_id / filename
                _write_chunked(content, csv_path)
                headers = sniff_headers(csv_path)
                store.set_mapping_pending(upload_id, csv_path=csv_path, sniffed_headers=headers)
            return RedirectResponse(url="/dashboard", status_code=303)

        # ── Multi-file consolidation: stage raws into a batch dir, group by layout ──
        batch_dir = settings.uploads_dir / f"_batch_{batch_id}"
        entries: list[FileEntry] = []
        for idx, (filename, content) in enumerate(processed_files):
            # Prefix with index to avoid collisions when files share a name
            staged = batch_dir / f"{idx:04d}_{filename}"
            _write_chunked(content, staged)
            entries.append(
                FileEntry(name=filename, path=str(staged), headers=sniff_headers(staged))
            )

        groups = group_files_by_signature(entries)

        if len(groups) == 1:
            # All files share one layout → merge straight away, then map once.
            ordered_groups = list(groups.items())
            unified_cols = unified_columns(groups)
            alignment = suggest_alignment(groups, unified_cols)  # identity for a single group
            upload_id = _finalize_consolidated_upload(
                report_type=report_type,
                engagement_id=engagement_id,
                batch_id=batch_id,
                ordered_groups=ordered_groups,
                alignment=alignment,
                unified_cols=unified_cols,
                source_names=[e.name for e in entries],
            )
            shutil.rmtree(batch_dir, ignore_errors=True)
            return RedirectResponse(
                url=f"/dashboard/uploads/{upload_id}/map-columns", status_code=303
            )

        # ── Schema mismatch across files → guided reconciliation screen ──
        store.create_batch(
            batch_id,
            report_type,
            engagement_id=engagement_id,
            files=[e.as_dict() for e in entries],
        )
        return RedirectResponse(url=f"/consolidate/reconcile/{batch_id}", status_code=303)

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
        return RedirectResponse(url=f"/dashboard/uploads/{upload_id}", status_code=303)

    raw_headers: list[str] = json.loads(upload["sniffed_headers"] or "[]")
    schema = get_schema(upload["report_type"])

    # Compute header signature for profile lookup
    header_signature = hashlib.sha256(
        json.dumps(sorted(raw_headers), sort_keys=True).encode()
    ).hexdigest()

    # Check for saved profile
    engagement_id = upload.get("engagement_id")
    saved_profile = store.find_profile_by_signature(
        upload["report_type"],
        header_signature,
        engagement_id=engagement_id,
    )

    # If profile found, use it; otherwise compute suggestions with scores
    profile_applied = False
    suggested: dict[str, str] = {}
    suggested_with_scores: dict[str, tuple[str, float]] = {}

    if saved_profile:
        suggested = json.loads(saved_profile["mapping_json"])
        profile_applied = True
    else:
        if schema:
            suggested_with_scores = schema.map_headers_with_scores(raw_headers)
            # Build suggested dict from fuzzy+exact matches (keys are raw_headers, values are canonicals)
            suggested = {
                raw_h: canonical for raw_h, (canonical, score) in suggested_with_scores.items()
            }

    canonical_fields = get_canonical_fields(upload["report_type"])

    # Invert suggested map: canonical -> raw_header (for the new UI direction)
    suggested_inverse = {canonical: raw_h for raw_h, canonical in suggested.items()}

    return templates.TemplateResponse(
        request=request,
        name="column_map.html",
        context={
            "upload": upload,
            "raw_headers": raw_headers,
            "suggested": suggested,
            "suggested_with_scores": suggested_with_scores,
            "suggested_inverse": suggested_inverse,
            "canonical_fields": canonical_fields,
            "profile_applied": profile_applied,
            "profile_id": saved_profile.get("profile_id") if saved_profile else None,
        },
    )


@router.post("/uploads/{upload_id}/map-columns")
async def do_map_columns(request: Request, upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    form = await request.form()
    raw_headers: list[str] = json.loads(upload["sniffed_headers"] or "[]")

    # Form fields are named map_<canonical> = raw_header (canonical fields are the fixed left side)
    canonical_fields = get_canonical_fields(upload["report_type"])
    user_mapping: dict[str, str] = {}
    for spec in canonical_fields:
        raw_header = str(form.get(f"map_{spec.canonical}", "") or "").strip()
        if raw_header and raw_header != "__skip__":
            user_mapping[raw_header] = spec.canonical

    raw_csv_path = upload["csv_path"] or ""
    blob_downloaded = False

    # If csv_path is a blob URL, download it to /tmp for ingestion
    if raw_csv_path.startswith("http"):
        import httpx as _httpx

        tmp_dir = settings.uploads_dir / upload_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        csv_path = tmp_dir / upload["filename"]
        async with _httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", raw_csv_path) as resp:
                with csv_path.open("wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        f.write(chunk)
        blob_downloaded = True
    else:
        csv_path = Path(raw_csv_path)
        if not csv_path.exists():
            raise HTTPException(status_code=500, detail="Uploaded CSV file not found on disk.")

    try:
        result = ingest_csv(csv_path, upload["report_type"], upload_id, user_mapping=user_mapping)

        # Import Parquet into DuckDB, then delete both Parquet and raw CSV from disk
        store.store_upload_data(upload_id, result.parquet_path)
        if blob_downloaded:
            csv_path.unlink(missing_ok=True)
            try:
                csv_path.parent.rmdir()
            except Exception:
                pass
        else:
            csv_path.unlink(missing_ok=True)
            try:
                csv_path.parent.rmdir()
            except Exception:
                pass

        store.set_upload_ready(
            upload_id,
            parquet_path=result.parquet_path,  # kept in DB record for reference
            row_count=result.total_rows,
            column_mapping=user_mapping,
        )

        # After successful ingestion, save the mapping as a profile
        header_signature = hashlib.sha256(
            json.dumps(sorted(raw_headers), sort_keys=True).encode()
        ).hexdigest()
        engagement_id = upload.get("engagement_id")
        username = request.session.get("username", "admin")
        store.save_mapping_profile(
            upload["report_type"],
            header_signature,
            json.dumps(user_mapping),
            engagement_id=engagement_id,
            created_by=username,
        )
    except Exception as exc:
        store.set_upload_failed(upload_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return RedirectResponse(url=f"/dashboard/uploads/{upload_id}", status_code=303)


# ---------------------------------------------------------------------------
# Delete upload
# ---------------------------------------------------------------------------


@router.post("/uploads/{upload_id}/delete")
async def delete_upload(upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    store.delete_upload(upload_id)
    return RedirectResponse(url="/dashboard", status_code=303)


# ---------------------------------------------------------------------------
# Upload detail
# ---------------------------------------------------------------------------


@router.get("/uploads/{upload_id}", response_class=HTMLResponse)
async def upload_detail(request: Request, upload_id: str):
    from fcmr_core.rules.registry import list_categories

    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    mapping_display: list[tuple[str, str]] = []
    if upload.get("column_mapping"):
        mapping_display = list(json.loads(upload["column_mapping"]).items())

    source_files: list[str] = []
    if upload.get("source_files_json"):
        source_files = json.loads(upload["source_files_json"])

    runs = store.list_runs(upload_id)
    categories = list_categories()

    # EAD analytics runs (engagement-scoped)
    engagement_id = request.session.get("engagement_id")
    ead_runs = store.list_ead_runs(engagement_id) if engagement_id else []

    return templates.TemplateResponse(
        request=request,
        name="upload_detail.html",
        context={
            "upload": upload,
            "runs": runs,
            "mapping_display": mapping_display,
            "source_files": source_files,
            "categories": categories,
            "ead_runs": ead_runs,
        },
    )


@router.get("/uploads/{upload_id}/preview", response_class=HTMLResponse)
async def preview_upload(request: Request, upload_id: str):
    upload = store.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload["status"] != "ready":
        return RedirectResponse(url=f"/dashboard/uploads/{upload_id}", status_code=303)

    try:
        df = store.get_upload_df(upload_id)
        preview_df = df.head(500).with_columns(
            [pl.col(c).cast(pl.Utf8, strict=False) for c in df.columns]
        )
        preview_cols = preview_df.columns
        preview_rows = preview_df.rows()
        col_count = len(preview_cols)
        row_count = len(preview_rows)
    except Exception:
        preview_cols = []
        preview_rows = []
        col_count = 0
        row_count = 0

    return templates.TemplateResponse(
        request=request,
        name="upload_preview.html",
        context={
            "upload": upload,
            "preview_cols": preview_cols,
            "preview_rows": preview_rows,
            "col_count": col_count,
            "row_count": row_count,
        },
    )
