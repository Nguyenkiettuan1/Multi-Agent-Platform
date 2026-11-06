"""Auth routes (login, logout, me, change password) and admin user management.

Routes are sync (`def`) on purpose: argon2 and the DB calls then run in
FastAPI's threadpool instead of blocking the event loop.

Nothing here may put a password, a session token, a cookie value or the
X-API-Key header into an audit row, a log line or an error message.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine
from core.observability.audit import write_audit
from core.security import sessions, users
from core.security.auth import (
    Principal,
    client_ip,
    require_admin,
    require_authenticated,
    require_csrf_header,
)
from core.security.passwords import dummy_verify, needs_rehash, verify_password
from core.security.throttle import begin_login_attempt, mark_succeeded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

BAD_LOGIN = "Invalid email or password"

# Column widths in platform.users, and the cap on submitted passwords. The password
# policy (12-128) only applies to NEW passwords; login/verify input is capped at 1024
# so a megabyte body cannot be fed to argon2.
_EMAIL_MAX = 320
_NAME_MAX = 200
_PASSWORD_INPUT_MAX = 1024

# Taken inside the "lock the last active admin" transaction, so concurrent
# deactivations are serialised (one bigint key: separate from throttle's two-int keys).
_LOCK_ADMIN_GUARD = 7303

# Control characters (NUL included) are rejected here: users.validate_email does not
# check them, and Postgres refuses NUL in text, which would surface as a 500 not a 422.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _check_email(value: str) -> str:
    value = value.strip()
    if _CONTROL_RE.search(value):
        raise ValueError("email must not contain control characters")
    return users.validate_email(value)  # format rule lives in one place (raises ValueError)


def _check_display_name(value: str) -> str:
    value = value.strip()
    if not value or _CONTROL_RE.search(value):
        raise ValueError("display_name must be non-empty text without control characters")
    return value


Email = Annotated[str, Field(min_length=3, max_length=_EMAIL_MAX), AfterValidator(_check_email)]
DisplayName = Annotated[str, Field(min_length=1, max_length=_NAME_MAX), AfterValidator(_check_display_name)]
PasswordInput = Annotated[str, Field(min_length=1, max_length=_PASSWORD_INPUT_MAX)]


class LoginRequest(BaseModel):
    email: Email
    password: PasswordInput


class ChangePasswordRequest(BaseModel):
    current_password: PasswordInput
    new_password: PasswordInput


class CreateUserRequest(BaseModel):
    email: Email
    display_name: DisplayName
    role: Literal["user", "admin"]
    password: PasswordInput


class SetActiveRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    password: PasswordInput


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["user", "admin"]
    must_change_password: bool


class AdminUserOut(UserOut):
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginResponse(BaseModel):
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    via: Literal["session", "api_key"]


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int


def _user_out(user: users.User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


def _admin_user_out(user: users.User) -> dict:
    return {**_user_out(user), "is_active": user.is_active, "created_at": user.created_at, "last_login_at": user.last_login_at}


def _audit(action: str, user_id: str | None, payload: dict | None = None) -> None:
    write_audit(trace_id=uuid.uuid4().hex, action=action, agent_name="auth", user_id=user_id, payload=payload)


def _target_payload(actor: Principal, target: users.User) -> dict:
    # Admin-action audit convention: the actor is the row's user_id, the target is
    # described here. Ids / email / role only, never a password or hash.
    return {"target_user_id": target.id, "email": target.email, "role": target.role, "actor_user_id": actor.user_id}


def _cookie_attrs() -> dict:
    return {
        "path": "/",
        "secure": get_settings().auth_cookie_secure,
        "httponly": True,
        "samesite": "strict",
    }


def _set_session_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        sessions.COOKIE_NAME,
        value,
        max_age=get_settings().auth_session_ttl_hours * 3600,
        **_cookie_attrs(),
    )


# --- login / logout / me / password ---------------------------------------------


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(require_csrf_header)])
def login(body: LoginRequest, request: Request, response: Response):
    email_norm = users.normalize_email(body.email)
    ip = client_ip(request)

    # Records this attempt as a failure BEFORE the slow check, under advisory locks
    # (see throttle.py), and refuses without hashing once the limits are reached.
    wait, attempt_id = begin_login_attempt(email_norm, ip)
    if wait is not None:
        raise HTTPException(
            status_code=429, detail="Too many attempts, try again later", headers={"Retry-After": str(wait)}
        )

    user = users.get_local_user_by_email(email_norm)
    if user is None or not user.is_active or not user.password_hash:
        # Spend the same hashing time as a real check, and answer identically for
        # unknown / deactivated accounts and wrong passwords.
        dummy_verify(body.password)
        _audit("auth_login_failed", None, {"email_norm": email_norm, "ip": ip})
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    if not verify_password(user.password_hash, body.password):
        _audit("auth_login_failed", user.id, {"email_norm": email_norm, "ip": ip})
        raise HTTPException(status_code=401, detail=BAD_LOGIN)

    mark_succeeded(attempt_id)
    # A login always gets a fresh token; the presented one is retired (session fixation).
    old_cookie = request.cookies.get(sessions.COOKIE_NAME)
    if old_cookie:
        sessions.revoke_session(old_cookie)
    cookie = sessions.issue_session(user.id, ip, request.headers.get("user-agent"))
    users.touch_last_login(user.id)
    if needs_rehash(user.password_hash):
        try:
            users.set_password(user.id, body.password, user.must_change_password)
        except users.PasswordPolicyError:
            # The policy got stricter since this password was set: keep the old
            # hash rather than refuse a correct login.
            logger.info("Skipped rehash for user %s: password no longer meets policy", user.id)
    _audit("auth_login", user.id, {"ip": ip})
    _set_session_cookie(response, cookie)
    return {"user": _user_out(user)}


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf_header)])
def logout(request: Request):
    """Public and idempotent: no cookie, a forged one or a dead session still gives 204."""
    out = Response(status_code=204)
    cookie = request.cookies.get(sessions.COOKIE_NAME)
    if cookie:
        session = sessions.resolve_session(cookie)
        sessions.revoke_session(cookie)
        if session is not None:
            _audit("auth_logout", session.user_id)
    out.delete_cookie(sessions.COOKIE_NAME, **_cookie_attrs())
    return out


@router.get("/auth/me", response_model=MeResponse)
def me(principal: Principal = Depends(require_authenticated)):
    # Built field by field: Principal.session_hash must never reach a response.
    return {
        "user": {
            "id": principal.user_id,
            "email": principal.email,
            "display_name": principal.display_name,
            "role": principal.role,
            "must_change_password": principal.must_change_password,
        },
        "via": principal.via,
    }


@router.post("/auth/password", status_code=204)
def change_password(body: ChangePasswordRequest, request: Request, principal: Principal = Depends(require_authenticated)):
    if principal.via != "session":
        raise HTTPException(status_code=403, detail="Changing a password requires a user session")
    # Same throttle as login, so a stolen session cannot be used to guess the current
    # password. The key "pw:<uuid>" (39 chars, fits email_norm VARCHAR(320)) can never
    # equal a real email_norm: those always contain "@", this one never does. The "ip"
    # is the same per-user key, not the client IP: the per-IP bucket is shared with
    # /auth/login, so using the real IP would let failed changes count against, and
    # eventually lock out, every login behind the same NAT. The per-user limit
    # (5 / 15 min) is the real protection here; this caller is already authenticated.
    throttle_key = f"pw:{principal.user_id}"
    wait, attempt_id = begin_login_attempt(throttle_key, throttle_key)
    if wait is not None:
        raise HTTPException(
            status_code=429, detail="Too many attempts, try again later", headers={"Retry-After": str(wait)}
        )
    user = users.get_user(principal.user_id)
    if user is None or not user.password_hash or not verify_password(user.password_hash, body.current_password):
        _audit("auth_password_change_failed", principal.user_id)
        # 400, not 401: 401 is reserved for "not authenticated" so an expired
        # session is never shown to the user as a wrong password.
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    mark_succeeded(attempt_id)
    if unicodedata.normalize("NFC", body.new_password) == unicodedata.normalize("NFC", body.current_password):
        raise HTTPException(status_code=422, detail="New password must differ from the current password")
    try:
        users.set_password(user.id, body.new_password, False)
    except users.PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    # Every session dies, the caller's included, and the caller gets a brand new
    # one: a possibly stolen cookie must not survive the change, and the token
    # that authorised it is not reused.
    sessions.revoke_all_for_user(user.id)
    cookie = sessions.issue_session(user.id, client_ip(request), request.headers.get("user-agent"))
    _audit("auth_password_changed", user.id)
    out = Response(status_code=204)
    _set_session_cookie(out, cookie)
    return out


# --- admin: users ---------------------------------------------------------------


@router.get("/admin/users", response_model=AdminUserList)
def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require_admin),
):
    items, total = users.list_users(limit, offset)
    return {"items": [_admin_user_out(u) for u in items], "total": total}


@router.post("/admin/users", status_code=201, response_model=AdminUserOut)
def create_user(body: CreateUserRequest, principal: Principal = Depends(require_admin)):
    try:
        user = users.create_user(body.email, body.display_name, body.role, body.password, must_change_password=True)
    except users.UserExists:
        raise HTTPException(status_code=409, detail="A user with this email already exists") from None
    except ValueError as exc:  # PasswordPolicyError and users' own field validation
        raise HTTPException(status_code=422, detail=str(exc)) from None
    _audit("user_created", principal.user_id, _target_payload(principal, user))
    return _admin_user_out(user)


def _local_user_or_404(user_id: uuid.UUID) -> users.User:
    user = users.get_user(str(user_id))
    if user is None or user.auth_provider != "local":
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _deactivate_unless_last_admin(user_id: str) -> bool:
    """Deactivate an active admin unless no other active admin would remain.

    The advisory lock serialises concurrent calls, so two admins locking each
    other at once cannot both pass the check and leave zero (a plain
    count-then-update would, under READ COMMITTED). False = refused.
    """
    with get_platform_engine().begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_ADMIN_GUARD})
        others = conn.execute(
            text(
                "SELECT count(*) FROM platform.users WHERE role = 'admin' AND is_active "
                "AND auth_provider = 'local' AND id <> CAST(:id AS uuid)"
            ),
            {"id": user_id},
        ).scalar_one()
        if others == 0:
            return False
        conn.execute(
            text(
                "UPDATE platform.users SET is_active = FALSE, updated_at = now() "
                "WHERE id = CAST(:id AS uuid) AND auth_provider = 'local'"
            ),
            {"id": user_id},
        )
    return True


@router.patch("/admin/users/{user_id}", response_model=AdminUserOut)
def set_user_active(user_id: uuid.UUID, body: SetActiveRequest, principal: Principal = Depends(require_admin)):
    target = _local_user_or_404(user_id)
    if not body.is_active and target.id == principal.user_id:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")

    if body.is_active:
        users.set_active(target.id, True)
    elif target.role == "admin" and target.is_active:
        if not _deactivate_unless_last_admin(target.id):
            raise HTTPException(status_code=409, detail="Cannot deactivate the last active admin")
    else:
        users.set_active(target.id, False)

    if not body.is_active:
        # Lock-out must bite on the very next request, not when the cookie expires.
        sessions.revoke_all_for_user(target.id)
    _audit(
        "user_enabled" if body.is_active else "user_disabled",
        principal.user_id,
        _target_payload(principal, target),
    )
    return _admin_user_out(users.get_user(target.id))


@router.post("/admin/users/{user_id}/password", status_code=204)
def reset_user_password(user_id: uuid.UUID, body: ResetPasswordRequest, principal: Principal = Depends(require_admin)):
    target = _local_user_or_404(user_id)
    try:
        users.set_password(target.id, body.password, True)
    except users.PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    sessions.revoke_all_for_user(target.id)
    _audit("user_password_reset", principal.user_id, _target_payload(principal, target))
    return Response(status_code=204)
