"""Desktop backend entry point for PyInstaller + Electron.

This module is the entry script for PyInstaller. It starts the FastAPI backend
on a configurable port. Electron spawns this and loads http://127.0.0.1:{port}.

In development: python -m uvicorn app.main:app --port 8765 (or use this script directly).
In production: PyInstaller creates an .exe that runs this on port 8765.
"""

import atexit
import os
import signal
import subprocess
import sys
from datetime import UTC

import uvicorn

# Get backend port from environment (Electron launcher sets to 8765; dev default 8000)
port = int(os.getenv("FCMR_BACKEND_PORT", "8000"))

# Pre-import startup self-log (before app import, so even import failures are visible)
log_dir = None
try:
    from fcmr_core.config import settings

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "backend.log"
    with open(log_file, "a") as f:
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        f.write(f"[{now}] backend process started (PID {os.getpid()}, port {port})\n")
except Exception:
    pass  # If logging fails, continue anyway

# Import the app object directly so PyInstaller can resolve it in frozen bundles.
# (String-based "app.main:app" fails in frozen mode because uvicorn can't import
# by string when modules are bundled into a single binary.)
try:
    from app.main import app  # noqa: E402
    from fcmr_core.catalog import store  # noqa: E402
except RuntimeError as e:
    # Catalog lock — attempt one self-heal via orphan reap, then retry
    if "locked" in str(e).lower():
        if log_dir:
            log_file = log_dir / "backend.log"
            with open(log_file, "a") as f:
                now = datetime.now(UTC).isoformat() if "datetime" in dir() else "?"
                f.write(f"[{now}] catalog locked, attempting orphan reap...\n")
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "sangir-backend.exe"],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    timeout=5,
                )
        except Exception:
            pass
        # Retry import once
        try:
            from app.main import app  # noqa: E402
            from fcmr_core.catalog import store  # noqa: E402
        except Exception as retry_err:
            if log_dir:
                log_file = log_dir / "backend.log"
                with open(log_file, "a") as f:
                    f.write(f"[?] fatal: {retry_err}\n")
            raise
    else:
        raise


def _cleanup():
    """Close catalog connection and exit cleanly (for graceful Electron shutdown)."""
    store.close_catalog()


if __name__ == "__main__":
    # Register cleanup on exit and SIGTERM/SIGINT
    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda sig, frame: (_cleanup(), exit(0)))
    signal.signal(signal.SIGINT, lambda sig, frame: (_cleanup(), exit(0)))

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
