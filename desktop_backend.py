"""Desktop backend entry point for PyInstaller + Electron.

This module is the entry script for PyInstaller. It starts the FastAPI backend
on a configurable port. Electron spawns this and loads http://127.0.0.1:{port}.

In development: python -m uvicorn app.main:app --port 8765 (or use this script directly).
In production: PyInstaller creates an .exe that runs this on port 8765.
"""

import atexit
import os
import signal

import uvicorn

# Import the app object directly so PyInstaller can resolve it in frozen bundles.
# (String-based "app.main:app" fails in frozen mode because uvicorn can't import
# by string when modules are bundled into a single binary.)
from app.main import app  # noqa: E402
from fcmr_core.catalog import store  # noqa: E402

# Get backend port from environment (Electron launcher sets to 8765; dev default 8000)
port = int(os.getenv("FCMR_BACKEND_PORT", "8000"))


def _cleanup():
    """Close catalog connection and exit cleanly (for graceful Electron shutdown)."""
    store.close_catalog()


if __name__ == "__main__":
    # Register cleanup on exit and SIGTERM/SIGINT
    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda sig, frame: (_cleanup(), exit(0)))
    signal.signal(signal.SIGINT, lambda sig, frame: (_cleanup(), exit(0)))

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
