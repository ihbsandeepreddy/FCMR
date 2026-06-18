"""Desktop backend entry point for PyInstaller + Electron.

This module is the entry script for PyInstaller. It starts the FastAPI backend
on a configurable port. Electron spawns this and loads http://127.0.0.1:{port}.

In development: python -m uvicorn app.main:app --port 8765 (or use this script directly).
In production: PyInstaller creates an .exe that runs this on port 8765.
"""

import os
import uvicorn

# Get backend port from environment (Electron launcher sets to 8765; dev default 8000)
port = int(os.getenv("FCMR_BACKEND_PORT", "8000"))

if __name__ == "__main__":
    # Run FastAPI on localhost (Electron loads this URL in BrowserWindow).
    # No auto-reload here: this is the Electron-spawned desktop launcher, and the
    # reloader subprocess would orphan on app quit. For web dev use:
    #   uvicorn app.main:app --reload
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
