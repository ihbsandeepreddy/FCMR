"""Vercel deployments must fail fast without an explicit session secret."""

from __future__ import annotations

import pytest


def test_vercel_requires_session_secret(monkeypatch):
    import fcmr_core.config as cfg

    monkeypatch.setattr(cfg, "_ON_VERCEL", True)
    with pytest.raises(ValueError):
        cfg.Settings(session_secret="")


def test_non_vercel_autogenerates_secret(monkeypatch):
    import fcmr_core.config as cfg

    monkeypatch.setattr(cfg, "_ON_VERCEL", False)
    s = cfg.Settings(session_secret="")
    assert s.session_secret  # auto-generated/loaded, not empty
