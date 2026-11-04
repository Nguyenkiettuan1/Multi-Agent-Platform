"""Session token generation and HMAC cookie signing. Stdlib only, no settings.

The raw token is what the browser holds; only token_hash() is stored in the
DB. The signature lets us reject forged cookies before touching the DB, and
rotating the secret invalidates every session at once.
"""

import base64
import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _signature(token: str, secret: str) -> str:
    if not secret:
        raise ValueError("secret must be a non-empty string")
    mac = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def sign(token: str, secret: str) -> str:
    return f"{token}.{_signature(token, secret)}"


def unsign(value: str, secret: str) -> str | None:
    """Return the token if the signature is valid, else None. Never raises on bad input."""
    if not secret:
        raise ValueError("secret must be a non-empty string")
    # Everything we sign is ASCII; rejecting the rest also keeps lone
    # surrogates from raising in the encode calls below.
    if not isinstance(value, str) or not value.isascii():
        return None
    # token_urlsafe never contains '.', but split on the last dot so the
    # signature (also dot-free) is always what is peeled off.
    token, dot, sig = value.rpartition(".")
    if not dot or not token or not sig:
        return None
    expected = _signature(token, secret)
    # Compare the encoded strings (as bytes) instead of decoding the supplied
    # signature: no base64 failure modes, and padded variants simply mismatch.
    if hmac.compare_digest(sig.encode("utf-8"), expected.encode("ascii")):
        return token
    return None
