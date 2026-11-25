"""Password hashing (argon2id) and password policy. Pure: no DB, no settings."""

import unicodedata
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Library defaults on purpose: they track current RFC 9106 guidance, and
# needs_rehash() lets us raise them later without a migration.
_hasher = PasswordHasher()

MIN_LENGTH = 12
MAX_LENGTH = 128  # bounds hashing cost for oversized input


def _normalize(password: str) -> str:
    # NFC before hashing, verifying and measuring (NIST SP 800-63B): some
    # Vietnamese IMEs emit decomposed (NFD) text, which would otherwise be a
    # different password and count as more characters than the user typed.
    return unicodedata.normalize("NFC", password)


def hash_password(password: str) -> str:
    return _hasher.hash(_normalize(password))


def verify_password(hashed: str, password: str) -> bool:
    # VerifyMismatchError is a VerificationError subclass; InvalidHashError is
    # a separate branch. Anything else (e.g. a non-str argument) is a bug.
    try:
        return _hasher.verify(hashed, _normalize(password))
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash("dummy-password-for-timing-equalisation")


def dummy_verify(password: str) -> None:
    """Spend the cost of one verification when the account does not exist.

    The hash is built on first use, not at import, so importing this module
    stays free (the hash costs tens of ms and 64 MiB).
    """
    verify_password(_dummy_hash(), password)


def validate_password(password: str, *, email: str) -> list[str]:
    """Return policy violations (empty list = acceptable)."""
    errors: list[str] = []
    password = _normalize(password)
    email = unicodedata.normalize("NFC", email)
    # len() counts Unicode code points (after NFC), so Vietnamese diacritics
    # are not penalised relative to ASCII.
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters.")
    elif len(password) > MAX_LENGTH:
        errors.append(f"Password must be at most {MAX_LENGTH} characters.")
    if password.casefold() == email.strip().casefold():
        errors.append("Password must not be the same as the email address.")
    return errors
