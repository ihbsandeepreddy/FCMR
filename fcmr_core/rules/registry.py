"""Rule registry and pipeline runner.

A rule is any callable with signature:
    rule(df: pl.DataFrame) -> pl.DataFrame

where the input frame has all canonical customer-master columns and the
output frame is the same frame with three columns appended per rule:
    _exc_{rule_id}_status   : "OK" | "WARN" | "ERROR"
    _exc_{rule_id}_code     : short exception code string or ""
    _exc_{rule_id}_desc     : human-readable description or ""

After all rules run, the reporting module collapses these into the final
wide and long CSVs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import polars as pl

RuleFn = Callable[[pl.DataFrame], pl.DataFrame]
ProgressFn = Callable[[int, int, str], None]  # (completed, total, rule_id)


@dataclass
class RuleMeta:
    rule_id: str
    description: str
    fn: RuleFn


_REGISTRY: list[RuleMeta] = []


def register(rule_id: str, description: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator to register a rule function."""

    def decorator(fn: RuleFn) -> RuleFn:
        _REGISTRY.append(RuleMeta(rule_id=rule_id, description=description, fn=fn))
        return fn

    return decorator


def list_rules() -> list[RuleMeta]:
    return list(_REGISTRY)


def run_pipeline(
    df: pl.DataFrame,
    on_progress: ProgressFn | None = None,
) -> pl.DataFrame:
    """Run all registered rules in registration order, returning an annotated frame.

    on_progress(completed, total, rule_id) is called after each rule if provided.
    It may raise an exception to abort the pipeline early (e.g. on cancellation).
    """
    _ensure_rules_loaded()
    total = len(_REGISTRY)
    for idx, meta in enumerate(_REGISTRY):
        df = meta.fn(df)
        if on_progress:
            on_progress(idx + 1, total, meta.rule_id)
    return df


def _ensure_rules_loaded() -> None:
    if _REGISTRY:
        return
    # Import triggers registration via @register decorators
    from fcmr_core.rules import ucid  # noqa: F401
    from fcmr_core.rules import kyc_format  # noqa: F401
    from fcmr_core.rules import pincode_address  # noqa: F401
    from fcmr_core.rules import duplicates  # noqa: F401
    from fcmr_core.rules import email  # noqa: F401
    from fcmr_core.rules import bank_account  # noqa: F401
    from fcmr_core.rules import beneficiary  # noqa: F401
