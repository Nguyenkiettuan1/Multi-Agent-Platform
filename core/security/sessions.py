"""Server-side login sessions (opaque token in a signed cookie, hash in the DB).

Stored in the DB rather than a stateless JWT so logout and account lock-out
take effect on the very next request.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine
from core.security.tokens import new_token, sign, token_hash, unsign

COOKIE_NAME = "ma_session"

# Column widths of platform.auth_sessions.
_IP_MAX = 64
_UA_MAX = 300


@dataclass(frozen=True)
class SessionUser:
    user_id: str
    email: str
    display_name: str
    role: str
    must_change_password: bool
    token_hash: str


def auth_secret() -> str:
    secret = get_settings().auth_secret_key
    if not secret:
        raise RuntimeError("AUTH_SECRET_KEY is not set")
    return secret


def issue_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    """Create a session and return the signed cookie value."""
    secret = auth_secret()
    token = new_token()
    with get_platform_engine().begin() as conn:
        # Only this user's expired rows: bounded work, no global sweep on the login path.
        conn.execute(
            text("DELETE FROM platform.auth_sessions WHERE user_id = CAST(:u AS uuid) AND expires_at < now()"),
            {"u": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO platform.auth_sessions (token_hash, user_id, expires_at, ip, user_agent)
                VALUES (:h, CAST(:u AS uuid), now() + make_interval(hours => :ttl), :ip, :ua)
                """
            ),
            {
                "h": token_hash(token),
                "u": user_id,
                "ttl": get_settings().auth_session_ttl_hours,
                "ip": ip[:_IP_MAX] if ip else None,
                "ua": user_agent[:_UA_MAX] if user_agent else None,
            },
        )
    return sign(token, secret)


def resolve_session(cookie_value: str) -> SessionUser | None:
    """None for a forged, unknown, expired, revoked session or a deactivated user."""
    token = unsign(cookie_value, auth_secret())
    if token is None:
        return None
    hashed = token_hash(token)
    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.id::text AS id, u.email, u.display_name, u.role, u.must_change_password
                FROM platform.auth_sessions s
                JOIN platform.users u ON u.id = s.user_id
                WHERE s.token_hash = :h AND s.revoked_at IS NULL AND s.expires_at > now()
                  AND u.is_active AND u.auth_provider = 'local'
                """
            ),
            {"h": hashed},
        ).first()
    if row is None:
        return None
    return SessionUser(row.id, row.email, row.display_name, row.role, row.must_change_password, hashed)


def revoke_session(cookie_value: str) -> bool:
    """Idempotent: False for a bad cookie or an already revoked/unknown session."""
    token = unsign(cookie_value, auth_secret())
    if token is None:
        return False
    with get_platform_engine().begin() as conn:
        result = conn.execute(
            text("UPDATE platform.auth_sessions SET revoked_at = now() WHERE token_hash = :h AND revoked_at IS NULL"),
            {"h": token_hash(token)},
        )
    return result.rowcount > 0


def revoke_all_for_user(user_id: str, except_hash: str | None = None) -> int:
    """Revoke every live session of the user, optionally keeping one (by token hash)."""
    with get_platform_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE platform.auth_sessions SET revoked_at = now()
                WHERE user_id = CAST(:u AS uuid) AND revoked_at IS NULL
                  AND (CAST(:keep AS text) IS NULL OR token_hash <> CAST(:keep AS text))
                """
            ),
            {"u": user_id, "keep": except_hash},
        )
    return result.rowcount
