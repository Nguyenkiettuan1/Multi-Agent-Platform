"""Pytest configuration and shared auth fixtures.

The auth fixtures log in through real rows in the dev platform DB (no dependency
overrides), so every route is exercised with the same cookie / API-key paths as
production. Cookie tests use https://testserver: the session cookie is Secure
and httpx would not send it back over http.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/multiagent",
)

AUTH_TEST_SECRET = "pytest-auth-secret-not-a-real-key"
AUTH_TEST_API_KEY = "pytest-api-key-value"
AUTH_TEST_PASSWORD = "correct horse battery"
CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}
TEST_EMAIL_PREFIX = "pytest-au-"
BASE_URL = "https://testserver"


def new_test_email() -> str:
    return f"{TEST_EMAIL_PREFIX}{uuid.uuid4().hex}@example.test"


def _purge_test_auth_rows() -> None:
    from core.database.engines import get_platform_engine

    like = f"{TEST_EMAIL_PREFIX}%@example.test"
    with get_platform_engine().begin() as conn:
        ids = [
            r[0]
            for r in conn.execute(
                text("DELETE FROM platform.users WHERE email LIKE :p RETURNING id::text"), {"p": like}
            )
        ]
        conn.execute(text("DELETE FROM platform.auth_login_attempts WHERE email_norm LIKE :p"), {"p": like})
        # audit_log has no FK to users: match on the ids / emails the tests produced.
        conn.execute(
            text(
                "DELETE FROM platform.audit_log WHERE user_id = ANY(:ids) "
                "OR payload->>'target_user_id' = ANY(:ids) OR payload->>'email_norm' LIKE :p"
            ),
            {"ids": ids, "p": like},
        )


@pytest.fixture
def auth_env(monkeypatch):
    """Inject the secrets the user's .env does not have, and clean test rows afterwards."""
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_secret_key", AUTH_TEST_SECRET)
    monkeypatch.setattr(settings, "api_key", AUTH_TEST_API_KEY)
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    try:
        yield settings
    finally:
        _purge_test_auth_rows()


@pytest.fixture
def make_user(auth_env):
    """Factory for local users (pytest-au-<uuid>@example.test); removed in auth_env teardown."""
    from core.security import users

    def _make(role="user", must_change_password=False, password=AUTH_TEST_PASSWORD, is_active=True):
        user = users.create_user(new_test_email(), "Test User", role, password, must_change_password)
        if not is_active:
            users.set_active(user.id, False)
        return user

    return _make


def make_client(headers=None):
    from fastapi.testclient import TestClient

    from gateway.main import app

    return TestClient(app, base_url=BASE_URL, headers=headers)


def _logged_in_client(user):
    from core.security import sessions

    client = make_client(CSRF_HEADERS)
    # domain/path match what the cookie jar stores for an app Set-Cookie (cookiejar appends ".local" to dotless hosts), so a rotated cookie replaces this one.
    client.cookies.set(
        sessions.COOKIE_NAME, sessions.issue_session(user.id, "203.0.113.9", "pytest"), domain="testserver.local", path="/"
    )
    client.auth_user = user  # tests that need the account behind the cookie
    return client


@pytest.fixture
def anon_client(auth_env):
    """No credentials and no CSRF header."""
    return make_client()


@pytest.fixture
def user_client(make_user):
    return _logged_in_client(make_user("user"))


@pytest.fixture
def admin_client(make_user):
    return _logged_in_client(make_user("admin"))


@pytest.fixture
def api_key_client(auth_env):
    return make_client({"X-API-Key": AUTH_TEST_API_KEY})
