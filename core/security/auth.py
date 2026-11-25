"""API authentication: session cookie or X-API-Key -> Principal."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from config import get_settings
from core.security import sessions, users
from core.security.passwords import dummy_verify

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "XMLHttpRequest"


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    display_name: str
    role: Literal["user", "admin"]
    must_change_password: bool
    via: Literal["session", "api_key"]
    # Token hash of the current cookie session (None for API keys), so the
    # password-change route can revoke every session except this one.
    session_hash: str | None = None


# The API key acts as the seeded 'service' system user (migration 010). Built
# statically: no DB hit per scripted request, and the id is a fixed constant.
_SERVICE_PRINCIPAL = Principal(
    user_id=users.SERVICE_USER_ID,
    email="service@system.invalid",
    display_name="Service",
    role="admin",
    must_change_password=False,
    via="api_key",
)


def _keys_equal(supplied: str, expected: str) -> bool:
    # Compare as bytes: compare_digest raises TypeError on non-ASCII str, which
    # a client could trigger with any header value.
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def warm_up() -> None:
    """Build the argon2 dummy hash now, so the first unknown-email login is not
    ~2x slower than later ones (a timing tell). Call once from the app lifespan."""
    dummy_verify("")


def client_ip(request: Request) -> str | None:
    """Peer address. uvicorn (proxy_headers defaults to on) rewrites it from X-Forwarded-For
    only for peers listed in FORWARDED_ALLOW_IPS (default 127.0.0.1); otherwise behind a
    proxy this is the proxy's address."""
    return request.client.host if request.client else None


def _check_csrf(request: Request) -> None:
    # A cross-site form or <img> cannot set a custom header, and a cross-origin
    # fetch that does would need a CORS preflight we do not grant.
    if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail="Missing CSRF header")


def require_csrf_header(request: Request) -> None:
    """For public state-changing routes (login, logout) that have no session to check."""
    _check_csrf(request)


def get_principal(request: Request, api_key: str | None = Security(_api_key_header)) -> Principal:
    # Sync on purpose: FastAPI runs it in the threadpool, so the DB lookup
    # does not block the event loop.
    if api_key:
        # An X-API-Key header selects the API-key path exclusively: a wrong
        # key never falls back to a (possibly valid) cookie.
        required = get_settings().api_key
        if not required or not _keys_equal(api_key, required):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return _SERVICE_PRINCIPAL

    cookie = request.cookies.get(sessions.COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = sessions.resolve_session(cookie)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _check_csrf(request)
    return Principal(
        user_id=session.user_id,
        email=session.email,
        display_name=session.display_name,
        role=session.role,  # type: ignore[arg-type]  # constrained by ck_users_role
        must_change_password=session.must_change_password,
        via="session",
        session_hash=session.token_hash,
    )


def require_authenticated(principal: Principal = Depends(get_principal)) -> Principal:
    """Authenticated, even if a password change is pending.

    Only for the routes that let the user finish that change: GET /auth/me and
    POST /auth/password. Chosen over a path check in require_user because the
    exemption is then visible on the route itself and cannot drift with
    prefixes or mount points. Logout is public and reads the cookie directly.
    """
    return principal


def require_user(principal: Principal = Depends(require_authenticated)) -> Principal:
    if principal.must_change_password:
        raise HTTPException(status_code=403, detail="Password change required")
    return principal


def require_admin(principal: Principal = Depends(require_user)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return principal

