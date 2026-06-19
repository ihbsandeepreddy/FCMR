"""Unit tests for KYC format validation rules."""

import polars as pl
import pytest

from fcmr_core.rules.kyc_format import (
    _verhoeff_valid,
    rule_aadhaar_format,
    rule_dob_validity,
    rule_email_format,
    rule_mobile_format,
    rule_pan_format,
    rule_passport_format,
    rule_voter_id_format,
)


def _df(**cols) -> pl.DataFrame:
    return pl.DataFrame({k: [v] for k, v in cols.items()})


def _status(df: pl.DataFrame, rule_id: str) -> str:
    return df[f"_exc_{rule_id}_status"][0]


def _code(df: pl.DataFrame, rule_id: str) -> str:
    return df[f"_exc_{rule_id}_code"][0]


# ---------------------------------------------------------------------------
# PAN
# ---------------------------------------------------------------------------


class TestPanFormat:
    def test_valid_pan(self):
        df = rule_pan_format(_df(pan="ABCPF1234A"))
        assert _status(df, "pan_format") == "OK"

    def test_missing_pan(self):
        # Blank PAN → OK; missing detection is handled by missing_data.pan_missing rule
        df = rule_pan_format(_df(pan=""))
        assert _status(df, "pan_format") == "OK"
        assert _code(df, "pan_format") == ""

    def test_invalid_format_short(self):
        df = rule_pan_format(_df(pan="ABC123"))
        assert _status(df, "pan_format") == "ERROR"
        assert _code(df, "pan_format") == "PAN_INVALID_FORMAT"

    def test_invalid_entity_char(self):
        # 4th char 'Z' is not a valid entity type
        df = rule_pan_format(_df(pan="ABCZF1234A"))
        assert _status(df, "pan_format") == "ERROR"
        assert _code(df, "pan_format") == "PAN_INVALID_ENTITY_CHAR"

    def test_lowercase_is_normalised_and_accepted(self):
        # Rule normalises to uppercase before checking, so lowercase input is accepted
        df = rule_pan_format(_df(pan="abcpf1234a"))
        assert _status(df, "pan_format") == "OK"

    @pytest.mark.parametrize("entity", ["P", "F", "H", "B", "C", "A", "G", "T"])
    def test_valid_entity_chars(self, entity):
        pan = f"ABC{entity}F1234A"
        df = rule_pan_format(_df(pan=pan))
        assert _status(df, "pan_format") == "OK", f"Entity char {entity} should be valid"


# ---------------------------------------------------------------------------
# Aadhaar
# ---------------------------------------------------------------------------


class TestAadhaarFormat:
    def test_verhoeff_known_valid(self):
        # Build a valid Aadhaar using the same algorithm as the generator
        import random

        from tests.generate_synthetic import _valid_aadhaar

        random.seed(1)
        valid = _valid_aadhaar()
        assert _verhoeff_valid(valid)

    def test_verhoeff_fails_on_flipped_digit(self):
        import random

        from tests.generate_synthetic import _valid_aadhaar

        random.seed(2)
        valid = _valid_aadhaar()
        corrupted = valid[:-1] + str((int(valid[-1]) + 1) % 10)
        assert not _verhoeff_valid(corrupted)

    def test_valid_aadhaar_rule(self):
        import random

        from tests.generate_synthetic import _valid_aadhaar

        random.seed(3)
        valid = _valid_aadhaar()
        df = rule_aadhaar_format(_df(aadhaar=valid))
        assert _status(df, "aadhaar_format") == "OK"

    def test_missing(self):
        # Blank Aadhaar → OK; missing detection handled by missing_data.aadhaar_missing rule
        df = rule_aadhaar_format(_df(aadhaar=""))
        assert _status(df, "aadhaar_format") == "OK"

    def test_wrong_length(self):
        df = rule_aadhaar_format(_df(aadhaar="123456789"))
        assert _code(df, "aadhaar_format") == "AADHAAR_INVALID_FORMAT"

    def test_invalid_prefix_0(self):
        # Starts with 0 — invalid
        df = rule_aadhaar_format(_df(aadhaar="012345678901"))
        assert _code(df, "aadhaar_format") == "AADHAAR_INVALID_PREFIX"

    def test_checksum_fail(self):
        import random

        from tests.generate_synthetic import _invalid_aadhaar

        random.seed(4)
        invalid = _invalid_aadhaar()
        df = rule_aadhaar_format(_df(aadhaar=invalid))
        assert _code(df, "aadhaar_format") == "AADHAAR_CHECKSUM_FAIL"


# ---------------------------------------------------------------------------
# Voter ID
# ---------------------------------------------------------------------------


class TestVoterIdFormat:
    def test_valid(self):
        df = rule_voter_id_format(_df(voter_id="ABC1234567"))
        assert _status(df, "voter_id_format") == "OK"

    def test_invalid_too_short(self):
        df = rule_voter_id_format(_df(voter_id="AB123"))
        assert _code(df, "voter_id_format") == "VOTER_ID_INVALID_FORMAT"

    def test_invalid_starts_with_digits(self):
        df = rule_voter_id_format(_df(voter_id="123ABCDEFG"))
        assert _code(df, "voter_id_format") == "VOTER_ID_INVALID_FORMAT"

    def test_missing(self):
        # Blank Voter ID → OK; missing detection handled by missing_data.voter_id_missing rule
        df = rule_voter_id_format(_df(voter_id=""))
        assert _status(df, "voter_id_format") == "OK"


# ---------------------------------------------------------------------------
# Passport
# ---------------------------------------------------------------------------


class TestPassportFormat:
    def test_valid(self):
        df = rule_passport_format(_df(passport="A1234567"))
        assert _status(df, "passport_format") == "OK"

    def test_invalid_first_char_Q(self):
        df = rule_passport_format(_df(passport="Q1234567"))
        assert _code(df, "passport_format") == "PASSPORT_INVALID_FORMAT"

    def test_invalid_first_char_Z(self):
        df = rule_passport_format(_df(passport="Z1234567"))
        assert _code(df, "passport_format") == "PASSPORT_INVALID_FORMAT"

    def test_optional_blank_is_ok(self):
        df = rule_passport_format(_df(passport=""))
        assert _status(df, "passport_format") == "OK"


# ---------------------------------------------------------------------------
# Mobile
# ---------------------------------------------------------------------------


class TestMobileFormat:
    @pytest.mark.parametrize("mobile", ["9876543210", "8001234567", "7001234567", "6001234567"])
    def test_valid_start_digits(self, mobile):
        df = rule_mobile_format(_df(mobile=mobile))
        assert _status(df, "mobile_format") == "OK"

    def test_invalid_starts_with_5(self):
        df = rule_mobile_format(_df(mobile="5123456789"))
        assert _code(df, "mobile_format") == "MOBILE_INVALID_FORMAT"

    def test_too_short(self):
        df = rule_mobile_format(_df(mobile="987654321"))
        assert _code(df, "mobile_format") == "MOBILE_INVALID_FORMAT"

    def test_with_country_code_prefix(self):
        df = rule_mobile_format(_df(mobile="+919876543210"))
        assert _status(df, "mobile_format") == "OK"


# ---------------------------------------------------------------------------
# DOB
# ---------------------------------------------------------------------------


class TestDobValidity:
    def test_valid_dob(self):
        df = rule_dob_validity(_df(dob="1990-06-15"))
        assert _status(df, "dob_validity") == "OK"

    def test_future_date(self):
        df = rule_dob_validity(_df(dob="2099-01-01"))
        assert _code(df, "dob_validity") == "DOB_FUTURE_DATE"

    def test_invalid_format(self):
        df = rule_dob_validity(_df(dob="not-a-date"))
        assert _code(df, "dob_validity") == "DOB_INVALID_FORMAT"

    def test_implausible_age_over_100(self):
        df = rule_dob_validity(_df(dob="1880-01-01"))
        assert _code(df, "dob_validity") == "DOB_AGE_IMPLAUSIBLE"

    def test_dd_mm_yyyy_format(self):
        df = rule_dob_validity(_df(dob="15-06-1985"))
        assert _status(df, "dob_validity") == "OK"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class TestEmailFormat:
    def test_valid(self):
        df = rule_email_format(_df(email="user@example.com"))
        assert _status(df, "email_format") == "OK"

    def test_no_at_sign(self):
        df = rule_email_format(_df(email="userexample.com"))
        assert _code(df, "email_format") == "EMAIL_INVALID_FORMAT"

    def test_missing(self):
        # Blank email → OK; missing detection handled by missing_data.email_missing rule
        df = rule_email_format(_df(email=""))
        assert _status(df, "email_format") == "OK"
