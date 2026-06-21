"""Authentication endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fcmr_core.catalog import store
from fcmr_core.logging_setup import get_logger
from fcmr_core.security import hash_password, verify_password

logger = get_logger(__name__)

router = APIRouter()
_templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Default admin user created on first run
_ADMIN_USERNAME = "admin"
_ADMIN_PASSWORD = "admin123"  # Must be changed on first login


def _ensure_admin() -> None:
    """Create default admin user if it doesn't exist."""
    try:
        user = store.get_user(_ADMIN_USERNAME)
        if user is None:
            pwd_hash, salt = hash_password(_ADMIN_PASSWORD)
            # Store salt:hash in password_hash field
            store.create_user(_ADMIN_USERNAME, f"{salt}:{pwd_hash}", "Admin User")
            print(
                f"\n🔐 Default admin user created: username='{_ADMIN_USERNAME}', password='{_ADMIN_PASSWORD}'"
            )
            print("   ⚠️  CHANGE THIS PASSWORD IMMEDIATELY ON FIRST LOGIN!\n")
    except Exception:
        pass  # User might already exist


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    """Login form."""
    return templates.TemplateResponse(request=request, name="login.html")


def _login_error(request: Request, message: str) -> HTMLResponse:
    """Re-render the login page with an inline error (instead of a raw 401 page)."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": message},
        status_code=401,
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Authenticate user and set session cookie."""
    invalid_msg = "Invalid username or password."
    user = store.get_user(username)
    if not user:
        return _login_error(request, invalid_msg)

    # Extract salt and hash
    pwd_parts = user["password_hash"].split(":")
    if len(pwd_parts) != 2:
        # Corrupt stored credential; do not leak details to the user.
        logger.error("Stored password for user '%s' is malformed", username)
        return _login_error(request, invalid_msg)
    salt, stored_hash = pwd_parts

    if not verify_password(password, stored_hash, salt):
        return _login_error(request, invalid_msg)

    # Create response and set session cookie
    response = RedirectResponse(url="/", status_code=303)
    request.session["username"] = username
    request.session["display_name"] = user["display_name"]

    # Log login event
    store.log_audit_event(action="login", username=username)

    return response


@router.post("/logout")
async def logout(request: Request):
    """Logout user and clear session."""
    username = request.session.get("username")

    # Log logout event (before clearing session)
    if username:
        store.log_audit_event(action="logout", username=username)

    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
