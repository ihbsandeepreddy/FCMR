"""SanGir Automations — FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.api import (
    auth,
    blob_upload,
    consolidate,
    downloads,
    ead_analytics,
    engagements,
    runs,
    system,
    uploads,
)
from app.api import settings as settings_api
from fcmr_core.catalog import store
from fcmr_core.catalog.store import init_catalog
from fcmr_core.config import settings
from fcmr_core.logging_setup import get_logger

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_catalog()
    auth._ensure_admin()
    store.init_settings()
    logger.info("Application startup: SanGir Automations ready")
    yield
    logger.info("Application shutdown")
    store.close_catalog()


app = FastAPI(
    title="SanGir Automations",
    description=(
        "Audit Analytics & Automated Solutions — "
        "Deterministic KYC and data-quality analytics for NBFC loan audits."
    ),
    version=settings.version,
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


# Version injection middleware
class VersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.app_version = settings.version
        return await call_next(request)


# Download cookie middleware — set dl_done cookie when a file download begins
class DownloadCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        dl_token = request.query_params.get("dl_token")
        if dl_token and response.status_code == 200:
            response.set_cookie(f"dl_done_{dl_token}", value="1", path="/", max_age=20)
        return response


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


# Session idle timeout middleware
class SessionIdleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if settings.session_idle_minutes > 0 and "username" in request.session:
            now = datetime.now(UTC)
            last_seen = request.session.get("_last_seen")

            # Initialize or check idle timeout
            if last_seen:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen)
                    idle_delta = now - last_seen_dt
                    if idle_delta > timedelta(minutes=settings.session_idle_minutes):
                        # Session expired; clear it
                        request.session.clear()
                        return RedirectResponse(url="/login", status_code=303)
                except (ValueError, TypeError):
                    pass  # Invalid timestamp, proceed anyway

            # Update last_seen
            request.session["_last_seen"] = now.isoformat()

        return await call_next(request)


# Add middlewares in reverse order (last added = innermost = runs first)
app.add_middleware(SessionIdleMiddleware)
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.add_middleware(VersionMiddleware)
app.add_middleware(DownloadCookieMiddleware)

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

# System info & monitoring routes — require login
app.include_router(system.router, prefix="/api", tags=["system"])

# Blob upload routes (token endpoint is public; register endpoint requires login)
app.include_router(blob_upload.router, prefix="", tags=["blob"])

# Schema reconciliation + consolidated-data downloads — require login
app.include_router(consolidate.router, prefix="", tags=["consolidate"])

# EAD Analytics — require login
app.include_router(ead_analytics.router, prefix="", tags=["ead_analytics"])
