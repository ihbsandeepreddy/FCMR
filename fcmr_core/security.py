"""Security utilities — password hashing, verification."""

from __future__ import annotations

import hashlib
import secrets


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash password with salt using PBKDF2-HMAC-SHA256 (100k iterations).

    Args:
        password: plaintext password
        salt: optional existing salt (if None, generates a new one)

    Returns:
        (hash_hex, salt) tuple for storage as "salt:hash"
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hash_obj.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify plaintext password against stored hash and salt.

    Args:
        password: plaintext password to verify
        password_hash: stored hash (hex string)
        salt: stored salt

    Returns:
        True if password matches, False otherwise
    """
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == password_hash
