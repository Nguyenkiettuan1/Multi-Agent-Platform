"""Auth routes (login/logout/me/password) and the route permission matrix.

Real rows in the dev platform DB; auth_env (conftest) injects the secrets and
removes every pytest-au-* row afterwards.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine
from core.security import sessions, users
from core.security.passwords import verify_password
from gateway import auth_routes
from conftest import AUTH_TEST_PASSWORD, CSRF_HEADERS, make_client, new_test_email

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
PASSWORD_URL = "/api/v1/auth/password"
BAD_LOGIN_DETAIL = "Invalid email or password"
NEW_PASSWORD = "another long passphrase"


def login(client, email, password=AUTH_TEST_PASSWORD, headers=CSRF_HEADERS):
    return client.post(LOGIN, json={"email": email, "password": password}, headers=headers)


def other_session_client(cookie_value):
    """A second browser holding an already issued cookie."""
    client = make_client(CSRF_HEADERS)
    client.cookies.set(sessions.COOKIE_NAME, cookie_value, domain="testserver.local", path="/")
    return client


# --- login ----------------------------------------------------------------------


def test_login_success_sets_hardened_cookie_and_returns_user(anon_client, make_user):
    user = make_user("user")
    r = login(anon_client, user.email.upper())  # email is case-insensitive
    assert r.status_code == 200
    assert r.json() == {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": "Test User",
            "role": "user",
            "must_change_password": False,
        }
    }
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith(f"{sessions.COOKIE_NAME}=")
    for attr in ("httponly", "secure", "samesite=strict", "path=/"):
        assert attr in cookie
    assert f"max-age={get_settings().auth_session_ttl_hours * 3600}" in cookie
    assert anon_client.get(ME).status_code == 200  # the cookie is usable


def test_cookie_secure_flag_follows_settings(anon_client, make_user, auth_env, monkeypatch):
    monkeypatch.setattr(auth_env, "auth_cookie_secure", False)
    r = login(anon_client, make_user().email)
    assert "secure" not in r.headers["set-cookie"].lower().replace("samesite", "")


def test_login_updates_last_login_at(anon_client, make_user):
    user = make_user()
    assert users.get_user(user.id).last_login_at is None
    login(anon_client, user.email)
    assert users.get_user(user.id).last_login_at is not None


def test_failed_logins_are_indistinguishable(anon_client, make_user):
    real = make_user()
    locked = make_user(is_active=False)
    responses = [
        login(anon_client, real.email, "not the password!!"),
        login(anon_client, new_test_email()),  # unknown email
        login(anon_client, locked.email),  # right password, deactivated account
    ]
    assert {r.status_code for r in responses} == {401}
    assert {r.json()["detail"] for r in responses} == {BAD_LOGIN_DETAIL}
    assert all("set-cookie" not in r.headers for r in responses)


def test_login_without_csrf_header_is_403(anon_client, make_user):
    assert login(anon_client, make_user().email, headers={}).status_code == 403


def test_sixth_attempt_is_429_with_retry_after_and_does_no_hashing(anon_client, make_user, monkeypatch):
    user = make_user()
    for _ in range(5):
        assert login(anon_client, user.email, "wrong password!!").status_code == 401

    calls = []
    monkeypatch.setattr(auth_routes, "verify_password", lambda *a: calls.append("verify") or True)
    monkeypatch.setattr(auth_routes, "dummy_verify", lambda *a: calls.append("dummy"))
    r = login(anon_client, user.email)  # correct password, still blocked
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many attempts, try again later"
    assert int(r.headers["retry-after"]) > 0
    assert calls == []


def test_unknown_email_is_throttled_like_a_real_one(anon_client):
    email = new_test_email()
    assert [login(anon_client, email).status_code for _ in range(6)] == [401] * 5 + [429]


def test_successful_login_resets_the_failure_count(anon_client, make_user):
    user = make_user()
    for _ in range(4):
        login(anon_client, user.email, "wrong password!!")
    assert login(anon_client, user.email).status_code == 200
    for _ in range(4):
        assert login(anon_client, user.email, "wrong password!!").status_code == 401


def test_login_issues_fresh_token_and_revokes_the_presented_cookie(anon_client, make_user):
    user = make_user()
    first = login(anon_client, user.email)
    old_cookie = anon_client.cookies.get(sessions.COOKIE_NAME)
    second = login(anon_client, user.email)
    new_cookie = anon_client.cookies.get(sessions.COOKIE_NAME)
    assert first.status_code == second.status_code == 200
    assert new_cookie != old_cookie
    assert sessions.resolve_session(old_cookie) is None  # fixation: old token is dead
    assert sessions.resolve_session(new_cookie) is not None


def test_login_rehashes_an_outdated_hash_and_keeps_must_change(anon_client, make_user, monkeypatch):
    user = make_user(must_change_password=True)
    before = users.get_user(user.id).password_hash
    monkeypatch.setattr(auth_routes, "needs_rehash", lambda _h: True)
    r = login(anon_client, user.email)
    after = users.get_user(user.id)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    assert after.password_hash != before and verify_password(after.password_hash, AUTH_TEST_PASSWORD)
    assert after.must_change_password is True


@pytest.mark.parametrize(
    "body",
    [
        {"email": "a" * 321, "password": "x"},
        {"email": "not-an-email", "password": "x"},
        {"email": "a@example.test", "password": "p" * 1025},
        {"email": "a@example.test", "password": ""},
        {"email": "a\x00b@example.test", "password": "x"},
        {"email": "a@example.test"},
    ],
)
def test_login_body_limits_are_422_not_500(anon_client, body):
    assert anon_client.post(LOGIN, json=body, headers=CSRF_HEADERS).status_code == 422


def test_login_with_vietnamese_password_and_nfd_input(anon_client, make_user):
    from unicodedata import normalize

    password = "Mật khẩu rất dài và có dấu"
    user = make_user(password=password)
    assert login(anon_client, user.email, normalize("NFD", password)).status_code == 200


# --- logout ---------------------------------------------------------------------


def test_logout_revokes_session_clears_cookie_and_is_idempotent(anon_client, make_user):
    user = make_user()
    login(anon_client, user.email)
    cookie = anon_client.cookies.get(sessions.COOKIE_NAME)

    r = anon_client.post(LOGOUT, headers=CSRF_HEADERS)
    assert r.status_code == 204 and r.content == b""
    cleared = r.headers["set-cookie"].lower()
    assert f"{sessions.COOKIE_NAME}=" in cleared and "max-age=0" in cleared
    for attr in ("httponly", "secure", "samesite=strict", "path=/"):
        assert attr in cleared
    assert sessions.resolve_session(cookie) is None
    assert other_session_client(cookie).get(ME).status_code == 401  # reused old cookie

    assert anon_client.post(LOGOUT, headers=CSRF_HEADERS).status_code == 204  # no cookie any more


def test_logout_with_garbage_cookie_is_204(anon_client):
    anon_client.cookies.set(sessions.COOKIE_NAME, "garbage.value")
    assert anon_client.post(LOGOUT, headers=CSRF_HEADERS).status_code == 204


def test_logout_without_csrf_header_is_403_and_keeps_session(anon_client, make_user):
    login(anon_client, make_user().email)
    assert anon_client.post(LOGOUT).status_code == 403
    assert anon_client.get(ME).status_code == 200


# --- me / csrf ------------------------------------------------------------------


def test_me_returns_user_and_via_without_session_hash(user_client):
    r = user_client.get(ME)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"user", "via"} and body["via"] == "session"
    assert set(body["user"]) == {"id", "email", "display_name", "role", "must_change_password"}
    token_hash = sessions.resolve_session(user_client.cookies.get(sessions.COOKIE_NAME)).token_hash
    assert token_hash not in r.text and "session_hash" not in r.text


def test_me_with_api_key_reports_service_user(api_key_client):
    body = api_key_client.get(ME).json()
    assert body["via"] == "api_key" and body["user"]["id"] == users.SERVICE_USER_ID


def test_me_without_credentials_is_401(anon_client):
    assert anon_client.get(ME).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [("POST", PASSWORD_URL), ("POST", "/api/v1/feedback"), ("POST", "/api/v1/chat")],
)
def test_unsafe_cookie_requests_need_the_csrf_header(user_client, method, path):
    r = user_client.request(method, path, json={}, headers={"X-Requested-With": ""})
    assert r.status_code == 403 and r.json()["detail"] == "Missing CSRF header"


def test_locked_user_cookie_dies_immediately(user_client):
    assert user_client.get(ME).status_code == 200
    users.set_active(user_client.auth_user.id, False)
    assert user_client.get(ME).status_code == 401


# --- change password ------------------------------------------------------------


def test_change_password_revokes_other_sessions_and_rotates_cookie(user_client):
    user = user_client.auth_user
    old_cookie = user_client.cookies.get(sessions.COOKIE_NAME)
    other_cookie = sessions.issue_session(user.id, None, "other browser")

    r = user_client.post(
        PASSWORD_URL, json={"current_password": AUTH_TEST_PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert r.status_code == 204
    new_cookie = user_client.cookies.get(sessions.COOKIE_NAME)
    assert new_cookie != old_cookie
    assert sessions.resolve_session(old_cookie) is None
    assert sessions.resolve_session(other_cookie) is None
    assert user_client.get(ME).status_code == 200  # the caller stays signed in
    stored = users.get_user(user.id)
    assert verify_password(stored.password_hash, NEW_PASSWORD) and not stored.must_change_password


def test_change_password_wrong_current_is_400_not_401(user_client):
    r = user_client.post(PASSWORD_URL, json={"current_password": "wrong password!!", "new_password": NEW_PASSWORD})
    assert r.status_code == 400 and r.json()["detail"] == "Current password is incorrect"
    assert user_client.get(ME).status_code == 200


@pytest.mark.parametrize(
    "new_password",
    ["short", "x" * 129, AUTH_TEST_PASSWORD, "p" * 1025],
    ids=["too-short", "too-long", "same-as-current", "over-cap"],
)
def test_change_password_policy_violations_are_422(user_client, new_password):
    r = user_client.post(PASSWORD_URL, json={"current_password": AUTH_TEST_PASSWORD, "new_password": new_password})
    assert r.status_code == 422
    stored = users.get_user(user_client.auth_user.id)
    assert verify_password(stored.password_hash, AUTH_TEST_PASSWORD)


def test_change_password_rejects_the_users_own_email(user_client):
    r = user_client.post(
        PASSWORD_URL,
        json={"current_password": AUTH_TEST_PASSWORD, "new_password": user_client.auth_user.email},
    )
    assert r.status_code == 422


def test_change_password_requires_a_user_session(api_key_client, anon_client):
    body = {"current_password": AUTH_TEST_PASSWORD, "new_password": NEW_PASSWORD}
    assert api_key_client.post(PASSWORD_URL, json=body).status_code == 403
    assert anon_client.post(PASSWORD_URL, json=body, headers=CSRF_HEADERS).status_code == 401


def test_old_password_stops_working_after_change(user_client, anon_client):
    user = user_client.auth_user
    user_client.post(PASSWORD_URL, json={"current_password": AUTH_TEST_PASSWORD, "new_password": NEW_PASSWORD})
    assert login(anon_client, user.email).status_code == 401
    assert login(anon_client, user.email, NEW_PASSWORD).status_code == 200


# --- must_change_password -------------------------------------------------------


def test_must_change_user_is_blocked_everywhere_but_the_exempt_routes(anon_client, make_user):
    user = make_user(must_change_password=True)
    r = login(anon_client, user.email)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True

    blocked = anon_client.get("/api/v1/chat/history", params={"session_id": "x"})
    assert blocked.status_code == 403 and blocked.json()["detail"] == "Password change required"
    assert anon_client.get("/api/v1/admin/users").status_code == 403
    assert anon_client.get(ME).status_code == 200  # exempt

    done = anon_client.post(
        PASSWORD_URL,
        json={"current_password": AUTH_TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=CSRF_HEADERS,
    )
    assert done.status_code == 204
    assert anon_client.get("/api/v1/chat/history", params={"session_id": "x"}).status_code == 200


def test_must_change_user_can_still_log_out(anon_client, make_user):
    login(anon_client, make_user(must_change_password=True).email)
    assert anon_client.post(LOGOUT, headers=CSRF_HEADERS).status_code == 204
    assert anon_client.get(ME).status_code == 401


# --- audit / logging hygiene ----------------------------------------------------


def _audit_rows(user, *actions):
    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, user_id, payload::text AS payload FROM platform.audit_log "
                "WHERE action = ANY(:a) AND (user_id = :uid OR payload->>'email_norm' = :email)"
            ),
            {"a": list(actions), "uid": user.id, "email": user.email},
        ).all()
    return rows


def test_audit_and_logs_never_contain_passwords_or_tokens(anon_client, make_user, caplog):
    caplog.set_level(logging.DEBUG)
    user = make_user()
    secret_password = "wrong but memorable pw"
    login(anon_client, user.email, secret_password)  # failure
    login(anon_client, user.email)  # success
    cookie = anon_client.cookies.get(sessions.COOKIE_NAME)
    anon_client.post(
        PASSWORD_URL,
        json={"current_password": AUTH_TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=CSRF_HEADERS,
    )
    anon_client.post(LOGOUT, headers=CSRF_HEADERS)

    rows = _audit_rows(user, "auth_login_failed", "auth_login", "auth_password_changed", "auth_logout")
    assert {r.action for r in rows} == {"auth_login_failed", "auth_login", "auth_password_changed", "auth_logout"}
    failed = next(r for r in rows if r.action == "auth_login_failed")
    assert user.email in failed.payload  # needed to investigate, still no secrets
    haystack = " ".join(r.payload for r in rows) + caplog.text
    for secret in (secret_password, AUTH_TEST_PASSWORD, NEW_PASSWORD, cookie):
        assert secret not in haystack


# --- permission matrix ----------------------------------------------------------

ADMIN_ROUTES = [
    ("GET", "/api/v1/models"),
    ("GET", "/api/v1/mcp/catalog"),
    ("GET", "/api/v1/admin/overview"),
    ("GET", "/api/v1/admin/stats"),
    ("GET", "/api/v1/admin/audit"),
    ("GET", "/api/v1/admin/feedback"),
    ("GET", "/api/v1/admin/knowledge/documents"),
    ("POST", "/api/v1/admin/feedback/abc/promote"),
    ("GET", "/api/v1/admin/users"),
    ("POST", "/api/v1/admin/users"),
]
USER_ROUTES = [
    ("GET", "/api/v1/chat/sessions"),
    ("GET", "/api/v1/chat/history?session_id=x"),
    ("POST", "/api/v1/chat"),
    ("POST", "/api/v1/chat/stream"),
    ("POST", "/api/v1/feedback"),
]


def test_health_is_public(anon_client):
    assert anon_client.get("/health").status_code == 200


@pytest.mark.parametrize("method,path", ADMIN_ROUTES + USER_ROUTES)
def test_anonymous_gets_401_everywhere(anon_client, method, path):
    assert anon_client.request(method, path, headers=CSRF_HEADERS).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_regular_user_gets_403_on_admin_routes(user_client, method, path):
    r = user_client.request(method, path)
    assert r.status_code == 403 and r.json()["detail"] == "Admin role required"


@pytest.mark.parametrize("method,path", USER_ROUTES)
def test_regular_user_passes_authentication_on_user_routes(user_client, method, path):
    # Empty body: chat/feedback answer 422 only after the auth dependency let us in.
    r = user_client.request(method, path, json={} if method == "POST" else None)
    assert r.status_code in (200, 422)


def test_api_key_acts_as_admin(api_key_client):
    assert api_key_client.get("/api/v1/admin/users").status_code == 200
    assert api_key_client.get("/api/v1/admin/knowledge/documents").status_code == 200


def test_wrong_api_key_is_401_even_with_a_valid_cookie(user_client):
    r = user_client.get(ME, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_empty_server_api_key_does_not_open_the_api(anon_client, auth_env, monkeypatch):
    monkeypatch.setattr(auth_env, "api_key", "")
    assert anon_client.get("/api/v1/chat/sessions").status_code == 401
    assert anon_client.get("/api/v1/chat/sessions", headers={"X-API-Key": ""}).status_code == 401


# --- lifespan fail-fast ---------------------------------------------------------


def _run_lifespan():
    from gateway.main import app, lifespan

    async def go():
        async with lifespan(app):
            pass

    asyncio.run(go())


def test_lifespan_refuses_to_start_without_auth_secret(auth_env, monkeypatch):
    monkeypatch.setattr(auth_env, "auth_secret_key", "")
    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
        _run_lifespan()


def test_lifespan_refuses_to_start_without_platform_database(auth_env, monkeypatch):
    monkeypatch.setattr(auth_env, "platform_database_url", None)
    with pytest.raises(RuntimeError, match="PLATFORM_DATABASE_URL"):
        _run_lifespan()


@pytest.fixture
def stubbed_startup(monkeypatch):
    """Lifespan without the real checkpointer / graph; only the auth start-up checks run."""
    import gateway.main as main

    async def fake_checkpointer():
        return object()

    monkeypatch.setattr(main, "create_checkpointer", fake_checkpointer)
    monkeypatch.setattr(main, "build_graph", lambda _cp: object())
    monkeypatch.setattr(main, "set_graph", lambda _g: None)
    # The real one replaces the root handlers, which would detach caplog.
    monkeypatch.setattr(main, "setup_logging", lambda _level: None)


@pytest.mark.parametrize(
    "secure,env,warns",
    [(False, "production", True), (False, "local", False), (True, "production", False)],
)
def test_lifespan_warns_about_insecure_cookie_outside_local(auth_env, stubbed_startup, monkeypatch, caplog, secure, env, warns):
    monkeypatch.setattr(auth_env, "auth_cookie_secure", secure)
    monkeypatch.setattr(auth_env, "app_env", env)
    with caplog.at_level(logging.WARNING, logger="gateway.main"):
        _run_lifespan()
    assert ("AUTH_COOKIE_SECURE is off" in caplog.text) is warns
