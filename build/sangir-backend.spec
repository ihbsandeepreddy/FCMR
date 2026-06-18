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
        # Web UI (Jinja2 templates, static assets)
        (os.path.join(ROOT, "app", "web", "templates"), "app/web/templates"),
        (os.path.join(ROOT, "app", "web", "static"), "app/web/static"),
        # Schema YAMLs (column mapping)
        (os.path.join(ROOT, "fcmr_core", "schemas"), "fcmr_core/schemas"),
        # Reference data (PIN master, etc.)
        (os.path.join(ROOT, "fcmr_core", "reference"), "fcmr_core/reference"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.server",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websocket.auto",
        "uvicorn.protocols.websocket.wsproto_impl",
        "duckdb",
        "polars",
        "pyarrow",
        "openpyxl",
        "pydantic_settings",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "black",
        "ruff",
        "pytest_asyncio",
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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="sangir-backend",
)
