"""get_principal / require_user / require_admin on a tiny FastAPI app.

Cookie tests use https://testserver: the session cookie is Secure and httpx
would not send it back over http. Rows are created against the dev platform DB
and removed in `finally`.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine
from core.security import sessions, users
from core.security.auth import (
    Principal,
    get_principal,
    require_admin,
    require_authenticated,
    require_csrf_header,
    require_user,
)

PASSWORD = "correct horse battery"
SECRET = "test-secret-for-auth-deps"
API_KEY = "test-api-key-value"
CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_secret_key", SECRET)
    monkeypatch.setattr(get_settings(), "api_key", API_KEY)


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/principal")
    def principal_get(p: Principal = Depends(get_principal)):
        return {"email": p.email, "role": p.role, "via": p.via, "user_id": p.user_id}

    @app.post("/principal")
    def principal_post(p: Principal = Depends(get_principal)):
        return {"via": p.via}

    @app.get("/user")
    def user_route(p: Principal = Depends(require_user)):
        return {"email": p.email}

    @app.get("/admin")
    def admin_route(p: Principal = Depends(require_admin)):
        return {"role": p.role}

    # Stand-ins for /auth/me and /auth/password, which must stay reachable
    # while a password change is pending.
    @app.get("/exempt")
    def exempt_route(p: Principal = Depends(require_authenticated)):
        return {"must_change_password": p.must_change_password, "session_hash": p.session_hash}

    @app.post("/public-csrf", dependencies=[Depends(require_csrf_header)])
    def public_csrf():
        return {"ok": True}

    return app


@pytest.fixture
def client():
    with TestClient(_build_app(), base_url="https://testserver") as c:
        yield c


@contextmanager
def _user_with_cookie(**kwargs):
    email = f"pytest-au-{uuid.uuid4().hex}@example.test"
    user = users.create_user(
        email, "Test User", kwargs.get("role", "user"), PASSWORD, kwargs.get("must_change_password", False)
    )
    try:
        yield user, sessions.issue_session(user.id, "203.0.113.9", "pytest")
    finally:
        with get_platform_engine().begin() as conn:
            conn.execute(text("DELETE FROM platform.users WHERE id = :id"), {"id": user.id})


# --- credential selection (section 3.0-F) -------------------------------------


def test_no_credentials_is_401(client):
    assert client.get("/principal").status_code == 401


def test_valid_api_key_is_service_admin(client):
    r = client.get("/principal", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["via"] == "api_key" and body["role"] == "admin"
    assert body["user_id"] == users.SERVICE_USER_ID


def test_api_key_post_needs_no_csrf_header(client):
    assert client.post("/principal", headers={"X-API-Key": API_KEY}).status_code == 200


def test_wrong_api_key_is_401(client):
    assert client.get("/principal", headers={"X-API-Key": "nope"}).status_code == 401


def test_wrong_api_key_does_not_fall_back_to_valid_cookie(client):
    with _user_with_cookie() as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/principal").status_code == 200  # cookie alone works
        assert client.get("/principal", headers={"X-API-Key": "nope"}).status_code == 401


def test_empty_server_api_key_rejects_any_header(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "")
    assert client.get("/principal", headers={"X-API-Key": "anything"}).status_code == 401
    # An empty server key must not make an empty-value match: the header is "absent" here.
    assert client.get("/principal").status_code == 401


def test_empty_api_key_header_counts_as_absent(client):
    with _user_with_cookie() as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/principal", headers={"X-API-Key": ""}).status_code == 200


def test_non_ascii_api_key_is_401_not_500(client):
    # hmac.compare_digest raises TypeError on non-ASCII str; we compare bytes.
    r = client.get("/principal", headers={"X-API-Key": "khóa".encode()})
    assert r.status_code == 401


# --- cookie + CSRF -------------------------------------------------------------


def test_valid_cookie_get_returns_session_principal(client):
    with _user_with_cookie() as (user, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        r = client.get("/principal")
        assert r.status_code == 200
        assert r.json() == {"email": user.email, "role": "user", "via": "session", "user_id": user.id}


def test_invalid_cookie_is_401(client):
    client.cookies.set(sessions.COOKIE_NAME, "garbage.value")
    assert client.get("/principal").status_code == 401


def test_cookie_post_without_csrf_header_is_403_with_is_200(client):
    with _user_with_cookie() as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.post("/principal").status_code == 403
        assert client.post("/principal", headers=CSRF).status_code == 200
        assert client.post("/principal", headers={"X-Requested-With": "other"}).status_code == 403


def test_revoked_session_is_401_immediately(client):
    with _user_with_cookie() as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/principal").status_code == 200
        sessions.revoke_session(cookie)
        assert client.get("/principal").status_code == 401


def test_require_csrf_header_dependency(client):
    assert client.post("/public-csrf").status_code == 403
    assert client.post("/public-csrf", headers=CSRF).status_code == 200


# --- roles and forced password change ------------------------------------------


def test_regular_user_is_forbidden_from_admin_route(client):
    with _user_with_cookie(role="user") as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/user").status_code == 200
        assert client.get("/admin").status_code == 403


def test_admin_cookie_and_api_key_reach_admin_route(client):
    with _user_with_cookie(role="admin") as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/admin").status_code == 200
    client.cookies.clear()
    assert client.get("/admin", headers={"X-API-Key": API_KEY}).status_code == 200


def test_must_change_password_blocks_all_but_exempt_routes(client):
    with _user_with_cookie(must_change_password=True) as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        for path in ("/user", "/admin"):
            r = client.get(path)
            assert r.status_code == 403 and r.json()["detail"] == "Password change required"
        exempt = client.get("/exempt")
        assert exempt.status_code == 200
        assert exempt.json()["must_change_password"] is True


def test_must_change_admin_gets_password_error_before_role_check(client):
    with _user_with_cookie(role="admin", must_change_password=True) as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        r = client.get("/admin")
        assert r.status_code == 403 and r.json()["detail"] == "Password change required"


def test_exempt_dependency_still_requires_authentication(client):
    assert client.get("/exempt").status_code == 401


def test_principal_exposes_session_hash_for_cookie_only(client):
    with _user_with_cookie() as (_, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        assert client.get("/exempt").json()["session_hash"] == sessions.resolve_session(cookie).token_hash
    client.cookies.clear()
    assert client.get("/exempt", headers={"X-API-Key": API_KEY}).json()["session_hash"] is None


def test_deactivated_user_cookie_is_401(client):
    with _user_with_cookie() as (user, cookie):
        client.cookies.set(sessions.COOKIE_NAME, cookie)
        users.set_active(user.id, False)
        assert client.get("/user").status_code == 401


def test_warm_up_runs_without_error():
    from core.security import passwords
    from core.security.auth import warm_up

    passwords._dummy_hash.cache_clear()
    assert passwords._dummy_hash.cache_info().currsize == 0
    warm_up()
    assert passwords._dummy_hash.cache_info().currsize == 1
