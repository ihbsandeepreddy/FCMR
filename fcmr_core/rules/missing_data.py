"""Missing data detection rules.

One rule per mandatory KYC field. Emits <FIELD>_MISSING (WARN) when the
field is blank; OK otherwise. Format/validity checking for the same fields
lives in kyc_format.py and pincode_address.py — those rules only fire when
data is present, so there is no double-reporting.

Covered: PAN, Aadhaar, Voter ID, Mobile, Email, DOB, Pincode.
Optional fields (Passport, DL, Bank Account) have no MISSING rule.
"""

from __future__ import annotations

import polars as pl

from fcmr_core.rules.registry import register


def _col_or_empty(df: pl.DataFrame, col: str) -> pl.Series:
    if col in df.columns:
        return df[col].cast(pl.Utf8, strict=False).fill_null("")
    return pl.Series(col, [""] * len(df), dtype=pl.Utf8)


def _annotate(
    df: pl.DataFrame, rule_id: str, statuses: list[str], codes: list[str], descs: list[str]
) -> pl.DataFrame:
    return df.with_columns(
        [
            pl.Series(f"_exc_{rule_id}_status", statuses, dtype=pl.Utf8),
            pl.Series(f"_exc_{rule_id}_code", codes, dtype=pl.Utf8),
            pl.Series(f"_exc_{rule_id}_desc", descs, dtype=pl.Utf8),
        ]
    )


def _missing_rule(
    df: pl.DataFrame,
    rule_id: str,
    col: str,
    code: str,
    label: str,
    *,
    strip_chars: str = "",
) -> pl.DataFrame:
    """Generic helper: blank → WARN/<code>; present → OK."""
    series = _col_or_empty(df, col)
    statuses, codes, descs = [], [], []
    for val in series:
        cleaned = (val or "").strip()
        if strip_chars:
            for ch in strip_chars:
                cleaned = cleaned.replace(ch, "")
        if not cleaned:
            statuses.append("WARN")
            codes.append(code)
            descs.append(f"{label} not provided")
        else:
            statuses.append("OK")
            codes.append("")
            descs.append("")
    return _annotate(df, rule_id, statuses, codes, descs)


@register("pan_missing", "PAN: field present check")
def rule_pan_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(df, "pan_missing", "pan", "PAN_MISSING", "PAN")


@register("aadhaar_missing", "Aadhaar: field present check")
def rule_aadhaar_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(
        df, "aadhaar_missing", "aadhaar", "AADHAAR_MISSING", "Aadhaar", strip_chars=" -"
    )


@register("voter_id_missing", "Voter ID: field present check")
def rule_voter_id_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(df, "voter_id_missing", "voter_id", "VOTER_ID_MISSING", "Voter ID")


@register("mobile_missing", "Mobile: field present check")
def rule_mobile_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(
        df, "mobile_missing", "mobile", "MOBILE_MISSING", "Mobile number", strip_chars=" -+"
    )


@register("email_missing", "Email: field present check")
def rule_email_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(df, "email_missing", "email", "EMAIL_MISSING", "Email")


@register("dob_missing", "Date of birth: field present check")
def rule_dob_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(df, "dob_missing", "dob", "DOB_MISSING", "Date of birth")


@register("pin_missing", "Pincode: field present check")
def rule_pin_missing(df: pl.DataFrame) -> pl.DataFrame:
    return _missing_rule(df, "pin_missing", "pincode", "PIN_MISSING", "Pincode")
