"""SanGir Automations — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from fcmr_core.catalog import store
from fcmr_core.catalog.store import init_catalog
from fcmr_core.config import settings
from app.api import auth, blob_upload, downloads, engagements, runs, settings as settings_api, uploads


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_catalog()
    auth._ensure_admin()
    store.init_settings()
    yield


app = FastAPI(
    title="SanGir Automations",
    description="Audit Analytics & Automated Solutions — Deterministic KYC and data-quality analytics for NBFC loan audits.",
    version="0.1.0",
    lifespan=lifespan,
)

# Ensure catalog + admin user exist — idempotent, safe to call on every cold start
_initialized = False

def _ensure_initialized() -> None:
    global _initialized
    if not _initialized:
        settings.ensure_dirs()
        init_catalog()
        auth._ensure_admin()
        store.init_settings()
        _initialized = True


# Login requirement middleware
class LoginRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        _ensure_initialized()
        public_paths = {"/login", "/static", "/api/blob-noop"}
        # Check if path starts with any public path
        is_public = any(request.url.path.startswith(p) for p in public_paths)
        if is_public:
            return await call_next(request)
        # Require login for all other paths (including /)
        if "username" not in request.session:
            return RedirectResponse(url="/login", status_code=303)
        return await call_next(request)

# Add middlewares in reverse order (last added = innermost = runs first)
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

# Static files
_static_dir = settings.base_dir / "app" / "web" / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Auth routes (login/logout) — public
app.include_router(auth.router, prefix="", tags=["auth"])

# Engagement routes (at /) — require login; "/" is the workspace selector
app.include_router(engagements.router, prefix="", tags=["engagements"])

# Upload/dashboard routes (at /dashboard) — require login; main analytics workspace
app.include_router(uploads.router, prefix="/dashboard", tags=["uploads"])

# Run/analytics routes (at /runs) — require login
app.include_router(runs.router, prefix="", tags=["runs"])

# Download routes — require login
app.include_router(downloads.router, prefix="", tags=["downloads"])

# Settings routes — require login
app.include_router(settings_api.router, prefix="", tags=["settings"])

# Blob upload routes (token endpoint is public; register endpoint requires login)
app.include_router(blob_upload.router, prefix="", tags=["blob"])
