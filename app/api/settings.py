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
