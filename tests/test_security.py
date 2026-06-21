"""Tests for security utilities."""

from __future__ import annotations

from fcmr_core.security import hash_password, verify_password


def test_hash_and_verify_password():
    """Test password hashing and verification round-trip."""
    password = "test_password_123"

    # Hash the password (generates a salt)
    pwd_hash, salt = hash_password(password)

    # Verify correct password
    assert verify_password(password, pwd_hash, salt), "Correct password should verify"

    # Verify incorrect password
    assert not verify_password("wrong_password", pwd_hash, salt), "Wrong password should not verify"


def test_hash_with_explicit_salt():
    """Test hashing with an explicit salt."""
    password = "my_password"
    explicit_salt = "test_salt_1234567890"

    # Hash with explicit salt
    pwd_hash, returned_salt = hash_password(password, explicit_salt)

    # Salt should be the same as input
    assert returned_salt == explicit_salt, "Returned salt should match input salt"

    # Verification should work
    assert verify_password(password, pwd_hash, explicit_salt)


def test_different_salts_produce_different_hashes():
    """Test that different salts produce different hashes for the same password."""
    password = "same_password"

    hash1, salt1 = hash_password(password)
    hash2, salt2 = hash_password(password)

    # Hashes should be different (different salts)
    assert hash1 != hash2, "Different salts should produce different hashes"
    assert salt1 != salt2, "Generated salts should be unique"
