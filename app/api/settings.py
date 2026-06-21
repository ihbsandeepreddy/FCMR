"""Settings management endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.backup import create_backup, list_backups
from fcmr_core.catalog import store
from fcmr_core.security import hash_password, verify_password

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Render settings page."""
    settings = store.list_settings()
    backups = list_backups()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"settings": settings, "backups": backups},
    )


@router.post("/settings")
async def update_setting(request: Request):
    """Update a setting."""
    form = await request.form()
    key = form.get("key", "").strip()
    value = form.get("value", "").strip()

    if key:
        store.set_setting(key, value)

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"settings": store.list_settings(), "message": f"✓ Setting '{key}' updated"},
    )


@router.get("/settings/backup")
async def backup_data(request: Request):
    """Create and download a backup of catalog + outputs."""
    try:
        backup_path = create_backup()
        return FileResponse(
            backup_path,
            media_type="application/zip",
            filename=backup_path.name,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={"settings": store.list_settings(), "message": f"✗ Backup failed: {exc}"},
            status_code=500,
        )


@router.post("/settings/change-password")
async def change_password(request: Request):
    """Change the logged-in user's password."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in")

    form = await request.form()
    current_password = form.get("current_password", "").strip()
    new_password = form.get("new_password", "").strip()
    new_password_confirm = form.get("new_password_confirm", "").strip()

    # Get user and verify current password
    user = store.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Parse stored password (format: "salt:hash")
    try:
        salt, pwd_hash = user["password_hash"].split(":")
    except ValueError:
        raise HTTPException(status_code=500, detail="Invalid password format in database")

    if not verify_password(current_password, pwd_hash, salt):
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "message": "✗ Current password is incorrect",
            },
            status_code=400,
        )

    # Validate new password
    if not new_password:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "message": "✗ New password cannot be empty",
            },
            status_code=400,
        )

    if new_password != new_password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "message": "✗ New passwords do not match",
            },
            status_code=400,
        )

    if len(new_password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "message": "✗ Password must be at least 8 characters",
            },
            status_code=400,
        )

    # Hash and update password
    new_hash, new_salt = hash_password(new_password)
    store.update_password(username, f"{new_salt}:{new_hash}")

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"settings": store.list_settings(), "message": "✓ Password changed successfully"},
    )


@router.post("/settings/restore-backup")
async def restore_backup(request: Request):
    """Restore data from a backup zip.

    DESTRUCTIVE OPERATION — requires explicit typed confirmation.
    NOTE: This endpoint is marked for human review before enabling in production.
    """
    from fcmr_core.backup import restore_backup

    form = await request.form()
    backup_filename = form.get("backup_filename", "").strip()
    confirmation = form.get("confirmation", "").strip()

    # Verify confirmation matches expected format: "restore-<filename>"
    expected_confirmation = f"restore-{backup_filename}"
    if confirmation != expected_confirmation:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "backups": list_backups(),
                "message": "✗ Confirmation mismatch. Restore cancelled.",
            },
            status_code=400,
        )

    # Locate backup file
    from fcmr_core.config import settings

    backup_path = settings.backups_dir / backup_filename
    if not backup_path.exists():
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "backups": list_backups(),
                "message": f"✗ Backup file not found: {backup_filename}",
            },
            status_code=404,
        )

    # Perform restore
    try:
        restore_backup(backup_path)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "backups": list_backups(),
                "message": "✓ Backup restored successfully. Please refresh your browser.",
            },
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "settings": store.list_settings(),
                "backups": list_backups(),
                "message": f"✗ Restore failed: {exc}",
            },
            status_code=500,
        )


@router.get("/audit", response_class=HTMLResponse)
async def audit_log_viewer(request: Request):
    """Display audit log (read-only, login-required)."""
    events = store.list_audit_events(limit=200)
    return templates.TemplateResponse(
        request=request,
        name="audit_log.html",
        context={"events": events},
    )
