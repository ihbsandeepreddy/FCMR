"""Shared pytest configuration.

Makes the whole suite hermetic: tests run against an isolated temporary data dir
and fixed test secrets, so they never touch a developer's real catalog. These are
set with ``setdefault`` so an explicit environment still wins (e.g. CI overrides).

This module MUST run before ``fcmr_core.config`` is imported anywhere, which pytest
guarantees by importing the root ``conftest.py`` before collecting test modules.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("FCMR_AADHAAR_HASH_SALT", "test-salt")
os.environ.setdefault("FCMR_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("FCMR_DATA_DIR", tempfile.mkdtemp(prefix="fcmr_test_"))
