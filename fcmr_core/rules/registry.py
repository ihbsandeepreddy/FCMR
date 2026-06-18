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


_NUMERIC_CANONICALS = {
    "loan_amount", "outstanding_principal", "emi_amount", "age",
    "sanctioned_amount", "disbursed_amount", "outstanding_balance",
}


def _coerce_str_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Cast any non-numeric, non-exception column to Utf8.

    Polars scan_csv can infer Int64 for columns like bank_account or pincode
    when all values are numeric. Rules call .strip() on Python values iterated
    from those columns, which raises AttributeError on int. This coercion runs
    once before the rule pipeline so every rule sees string values.
    """
    casts = []
    for col in df.columns:
        if col.startswith("_exc_"):
            continue
        if col in _NUMERIC_CANONICALS:
            continue
        if df[col].dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                             pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                             pl.Float32, pl.Float64):
            casts.append(pl.col(col).cast(pl.Utf8, strict=False))
    if casts:
        df = df.with_columns(casts)
    return df


def run_pipeline(df: pl.DataFrame) -> pl.DataFrame:
    """Run all registered rules in registration order, returning an annotated frame."""
    _ensure_rules_loaded()
    df = _coerce_str_columns(df)
    for meta in _REGISTRY:
        df = meta.fn(df)
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
