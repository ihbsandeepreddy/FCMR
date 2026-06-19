# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for SanGir Automations desktop backend.

Build: pyinstaller build/sangir-backend.spec
Output: dist/sangir-backend/ (one-dir bundle with all deps)

SPECPATH is the directory containing this spec file (build/).
ROOT is the repo root (one level up).
"""

import os

# SPECPATH is a PyInstaller built-in pointing to the spec file directory (build/)
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "desktop_backend.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Version file (read by config.py in frozen mode)
        (os.path.join(ROOT, "package.json"), "."),
        # Web UI (Jinja2 templates, static assets)
        (os.path.join(ROOT, "app", "web", "templates"), "app/web/templates"),
        (os.path.join(ROOT, "app", "web", "static"), "app/web/static"),
        # Schema YAMLs (column mapping)
        (os.path.join(ROOT, "fcmr_core", "schemas"), "fcmr_core/schemas"),
        # Reference data (PIN master, etc.)
        (os.path.join(ROOT, "fcmr_core", "reference"), "fcmr_core/reference"),
    ],
    hiddenimports=[
        # uvicorn internals
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.server",
        "uvicorn.config",
        "uvicorn.main",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websocket",
        "uvicorn.protocols.websocket.auto",
        "uvicorn.protocols.websocket.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # data stack
        "duckdb",
        "polars",
        "polars.datatypes",
        "pyarrow",
        "pyarrow.vendored",
        "openpyxl",
        "openpyxl.styles",
        "openpyxl.utils",
        # pydantic / fastapi
        "pydantic_settings",
        "pydantic",
        "pydantic.deprecated",
        "pydantic.v1",
        "anyio",
        "anyio.abc",
        "anyio._backends._asyncio",
        "starlette.middleware.sessions",
        # stdlib extras sometimes missed by PyInstaller
        "email.mime.text",
        "email.mime.multipart",
        "multipart",
        "python_multipart",
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "black",
        "ruff",
        "pytest_asyncio",
        "tkinter",
        "matplotlib",
        "scipy",
        "notebook",
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sangir-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # UPX disabled: some antivirus software quarantines UPX-packed exes
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# One-dir bundle: produces dist/sangir-backend/ containing sangir-backend.exe
# plus all dependencies. Electron loads it from process.resourcesPath/sangir-backend/.
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,   # UPX disabled across all bundled DLLs
    upx_exclude=[],
    name="sangir-backend",
)
