"""Unit tests for PIN code and address validation rules."""

import polars as pl

from fcmr_core.rules.pincode_address import (
    rule_address_completeness,
    rule_pincode_exists,
    rule_state_pin_match,
)


def _df(**cols) -> pl.DataFrame:
    return pl.DataFrame({k: [v] for k, v in cols.items()})


def _status(df: pl.DataFrame, rule_id: str) -> str:
    return df[f"_exc_{rule_id}_status"][0]


def _code(df: pl.DataFrame, rule_id: str) -> str:
    return df[f"_exc_{rule_id}_code"][0]


class TestPincodeExists:
    def test_known_valid_pin(self):
        df = rule_pincode_exists(_df(pincode="110001"))
        assert _status(df, "pincode_exists") == "OK"

    def test_known_invalid_pin(self):
        df = rule_pincode_exists(_df(pincode="999999"))
        assert _code(df, "pincode_exists") == "PIN_NOT_FOUND"

    def test_wrong_format_5_digits(self):
        df = rule_pincode_exists(_df(pincode="11000"))
        assert _code(df, "pincode_exists") == "PIN_INVALID_FORMAT"

    def test_missing_pin(self):
        # Blank pincode → OK; missing detection handled by missing_data.pin_missing rule
        df = rule_pincode_exists(_df(pincode=""))
        assert _status(df, "pincode_exists") == "OK"
        assert _code(df, "pincode_exists") == ""


class TestStatePinMatch:
    def test_correct_state(self):
        df = rule_state_pin_match(_df(pincode="110001", state="delhi"))
        assert _status(df, "state_pin_match") == "OK"

    def test_wrong_state(self):
        df = rule_state_pin_match(_df(pincode="110001", state="maharashtra"))
        assert _code(df, "state_pin_match") == "STATE_PIN_MISMATCH"

    def test_missing_state(self):
        # Missing state is skipped here (address_completeness handles it); no double-flag.
        df = rule_state_pin_match(_df(pincode="110001", state=""))
        assert _status(df, "state_pin_match") == "OK"

    def test_known_pin_karnataka(self):
        df = rule_state_pin_match(_df(pincode="560001", state="karnataka"))
        assert _status(df, "state_pin_match") == "OK"

    def test_known_pin_wrong_state(self):
        df = rule_state_pin_match(_df(pincode="560001", state="delhi"))
        assert _code(df, "state_pin_match") == "STATE_PIN_MISMATCH"


class TestAddressCompleteness:
    def test_all_fields_present(self):
        df = rule_address_completeness(
            _df(
                address_line1="123 Main St",
                city="Mumbai",
                state="Maharashtra",
                pincode="400001",
            )
        )
        assert _status(df, "address_completeness") == "OK"

    def test_missing_pincode(self):
        df = rule_address_completeness(
            _df(
                address_line1="123 Main St",
                city="Mumbai",
                state="Maharashtra",
                pincode="",
            )
        )
        assert _code(df, "address_completeness") == "ADDRESS_INCOMPLETE"

    def test_missing_multiple_fields(self):
        df = rule_address_completeness(
            _df(
                address_line1="",
                city="",
                state="Maharashtra",
                pincode="400001",
            )
        )
        assert _code(df, "address_completeness") == "ADDRESS_INCOMPLETE"
