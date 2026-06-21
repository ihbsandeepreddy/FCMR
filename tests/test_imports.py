"""Smoke-import every module so packaging/import regressions fail in CI, not on a
user's desktop. Also asserts the FastAPI app object is constructible.
"""

from __future__ import annotations

import importlib

import pytest

FCMR_MODULES = [
    "fcmr_core.config",
    "fcmr_core.logging_setup",
    "fcmr_core.backup",
    "fcmr_core.security",
    "fcmr_core.catalog.store",
    "fcmr_core.ingestion.pipeline",
    "fcmr_core.ingestion.consolidation",
    "fcmr_core.schemas.loader",
    "fcmr_core.rules.registry",
    "fcmr_core.rules.kyc_format",
    "fcmr_core.rules.duplicates",
    "fcmr_core.rules.ucid",
    "fcmr_core.rules.beneficiary",
    "fcmr_core.rules.missing_data",
    "fcmr_core.rules.pincode_address",
    "fcmr_core.rules.email",
    "fcmr_core.rules.bank_account",
    "fcmr_core.reporting.builder",
    "fcmr_core.reporting.aggregation",
    "fcmr_core.reporting.charts",
    "fcmr_core.reporting.excel_style",
    "fcmr_core.reporting.workpaper",
    "fcmr_core.sampling.sample",
    "fcmr_core.sampling.stratification",
    "fcmr_core.sampling.icai_table",
    "fcmr_core.reference.pin_master",
    "fcmr_core.analytics.ead_analytics",
    "fcmr_core.analytics.ead_summary",
    "fcmr_core.analytics.cm_analytics",
    "fcmr_core.analytics.cm_summary",
]

ENTRY_MODULES = ["app.main", "api.index", "desktop_backend"]


@pytest.mark.parametrize("mod", FCMR_MODULES + ENTRY_MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_app_is_fastapi():
    from fastapi import FastAPI

    from app.main import app

    assert isinstance(app, FastAPI)
