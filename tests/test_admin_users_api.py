"""Admin user management API (/api/v1/admin/users).

Real rows in the dev platform DB. The "last active admin" tests need a known
admin population, so they briefly deactivate any real local admins and restore
exactly those in `finally`.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import text

from conftest import AUTH_TEST_PASSWORD, CSRF_HEADERS, make_client, new_test_email
from core.database.engines import get_platform_engine
from core.security import sessions, users

BASE = "/api/v1/admin/users"
ADMIN_USER_KEYS = {
    "id", "email", "display_name", "role", "must_change_password", "is_active", "created_at", "last_login_at",
}
NEW_PASSWORD = "a brand new passphrase"


def create_body(**over):
    body = {"email": new_test_email(), "display_name": "Người Dùng Mới", "role": "user", "password": AUTH_TEST_PASSWORD}
    return {**body, **over}


# --- permissions ----------------------------------------------------------------


def test_regular_user_is_forbidden_on_every_user_admin_route(user_client):
    other = str(uuid.uuid4())
    assert user_client.get(BASE).status_code == 403
    assert user_client.post(BASE, json=create_body()).status_code == 403
    assert user_client.patch(f"{BASE}/{other}", json={"is_active": False}).status_code == 403
    assert user_client.post(f"{BASE}/{other}/password", json={"password": NEW_PASSWORD}).status_code == 403


# --- list -----------------------------------------------------------------------


def test_list_excludes_system_users_and_reports_total(admin_client, make_user):
    created = make_user("user")
    r = admin_client.get(BASE, params={"limit": 200})
    assert r.status_code == 200
    body = r.json()
    ids = {i["id"] for i in body["items"]}
    assert created.id in ids
    assert not ids & {users.LEGACY_USER_ID, users.SERVICE_USER_ID}
    assert body["total"] >= len(body["items"]) >= 2
    assert set(body["items"][0]) == ADMIN_USER_KEYS
    assert "password_hash" not in r.text


def test_list_pages_with_limit_and_offset(admin_client, make_user):
    make_user(), make_user()
    first = admin_client.get(BASE, params={"limit": 1, "offset": 0}).json()
    second = admin_client.get(BASE, params={"limit": 1, "offset": 1}).json()
    assert len(first["items"]) == len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["total"] == second["total"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_list_rejects_bad_paging(admin_client, params):
    assert admin_client.get(BASE, params=params).status_code == 422


# --- create ---------------------------------------------------------------------


def test_create_returns_admin_user_forces_password_change_and_can_log_in(admin_client, anon_client):
    body = create_body(role="admin")
    r = admin_client.post(BASE, json=body)
    assert r.status_code == 201
    created = r.json()
    assert set(created) == ADMIN_USER_KEYS
    assert created["email"] == body["email"] and created["role"] == "admin"
    assert created["must_change_password"] is True and created["is_active"] is True
    assert created["last_login_at"] is None and body["password"] not in r.text

    login = anon_client.post(
        "/api/v1/auth/login", json={"email": body["email"], "password": body["password"]}, headers=CSRF_HEADERS
    )
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True


def test_create_duplicate_email_is_409_case_insensitively(admin_client):
    body = create_body()
    assert admin_client.post(BASE, json=body).status_code == 201
    r = admin_client.post(BASE, json={**body, "email": body["email"].upper()})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "over",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"password": "p" * 1025},
        {"role": "root"},
        {"email": "not-an-email"},
        {"email": "a" * 321},
        {"email": "a\x00b@example.test"},
        {"display_name": "d" * 201},
        {"display_name": ""},
        {"display_name": "bad\x00name"},
    ],
    ids=["short-pw", "long-pw", "over-cap-pw", "bad-role", "bad-email", "long-email", "nul-email", "long-name", "empty-name", "nul-name"],
)
def test_create_validation_is_422_never_500(admin_client, over):
    assert admin_client.post(BASE, json=create_body(**over)).status_code == 422


def test_create_rejects_password_equal_to_email(admin_client):
    email = new_test_email()
    assert admin_client.post(BASE, json=create_body(email=email, password=email)).status_code == 422


def test_create_accepts_max_length_fields(admin_client):
    local = "a" * (320 - len("@example.test") - len("pytest-au-"))
    email = f"pytest-au-{local}@example.test"
    assert len(email) == 320
    r = admin_client.post(BASE, json=create_body(email=email, display_name="đ" * 200))
    assert r.status_code == 201


# --- activate / deactivate ------------------------------------------------------


def test_deactivate_revokes_sessions_blocks_login_and_reactivate_restores(admin_client, make_user, anon_client):
    target = make_user("user")
    target_cookie = sessions.issue_session(target.id, None, "pytest")

    r = admin_client.patch(f"{BASE}/{target.id}", json={"is_active": False})
    assert r.status_code == 200
    assert set(r.json()) == ADMIN_USER_KEYS and r.json()["is_active"] is False
    assert sessions.resolve_session(target_cookie) is None
    login = anon_client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": AUTH_TEST_PASSWORD}, headers=CSRF_HEADERS
    )
    assert login.status_code == 401

    back = admin_client.patch(f"{BASE}/{target.id}", json={"is_active": True})
    assert back.status_code == 200 and back.json()["is_active"] is True


def test_admin_cannot_lock_themselves(admin_client):
    r = admin_client.patch(f"{BASE}/{admin_client.auth_user.id}", json={"is_active": False})
    assert r.status_code == 409
    assert users.get_user(admin_client.auth_user.id).is_active is True


@pytest.mark.parametrize("system_id", [users.LEGACY_USER_ID, users.SERVICE_USER_ID])
def test_system_users_are_404_for_every_mutation(admin_client, system_id):
    before = users.get_user(system_id)
    assert admin_client.patch(f"{BASE}/{system_id}", json={"is_active": False}).status_code == 404
    assert admin_client.post(f"{BASE}/{system_id}/password", json={"password": NEW_PASSWORD}).status_code == 404
    assert users.get_user(system_id) == before


def test_unknown_user_is_404_and_malformed_id_is_422(admin_client):
    unknown = str(uuid.uuid4())
    assert admin_client.patch(f"{BASE}/{unknown}", json={"is_active": False}).status_code == 404
    assert admin_client.post(f"{BASE}/{unknown}/password", json={"password": NEW_PASSWORD}).status_code == 404
    assert admin_client.patch(f"{BASE}/not-a-uuid", json={"is_active": False}).status_code == 422


def test_patch_requires_is_active(admin_client, make_user):
    target = make_user()
    assert admin_client.patch(f"{BASE}/{target.id}", json={}).status_code == 422


@pytest.fixture
def sole_admins():
    """Deactivate every real local admin for the duration of the test (restored in finally)."""
    with get_platform_engine().begin() as conn:
        ids = [
            r[0]
            for r in conn.execute(
                text(
                    "UPDATE platform.users SET is_active = FALSE WHERE role = 'admin' AND is_active "
                    "AND auth_provider = 'local' AND email NOT LIKE 'pytest-au-%' RETURNING id::text"
                )
            )
        ]
    try:
        yield
    finally:
        with get_platform_engine().begin() as conn:
            conn.execute(text("UPDATE platform.users SET is_active = TRUE WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids})


def test_last_active_admin_cannot_be_locked_by_another_admin(sole_admins, make_user, api_key_client):
    # The API-key principal is a system admin: it is allowed to act, but does not count as an active admin.
    only = make_user("admin")
    r = api_key_client.patch(f"{BASE}/{only.id}", json={"is_active": False})
    assert r.status_code == 409
    assert users.get_user(only.id).is_active is True


def test_one_of_two_admins_can_be_locked(sole_admins, make_user, admin_client):
    other = make_user("admin")
    assert admin_client.patch(f"{BASE}/{other.id}", json={"is_active": False}).status_code == 200


def test_two_admins_locking_each_other_concurrently_never_leave_zero(sole_admins, make_user):
    for _ in range(5):
        a, b = make_user("admin"), make_user("admin")
        clients = {}
        for u in (a, b):
            c = make_client(CSRF_HEADERS)
            c.cookies.set(sessions.COOKIE_NAME, sessions.issue_session(u.id, None, "pytest"))
            clients[u.id] = c
        barrier = threading.Barrier(2)
        results = {}

        def lock(actor, victim):
            barrier.wait()
            results[actor.id] = clients[actor.id].patch(f"{BASE}/{victim.id}", json={"is_active": False}).status_code

        threads = [threading.Thread(target=lock, args=(a, b)), threading.Thread(target=lock, args=(b, a))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert users.count_active_admins() >= 1, results
        assert sorted(results.values()).count(200) == 1, results  # the loser gets 409 (or 401 once revoked)
        for u in (a, b):  # next round starts from a clean slate
            users.set_active(u.id, False)


# --- admin password reset -------------------------------------------------------


def test_reset_password_revokes_sessions_and_forces_change(admin_client, make_user, anon_client):
    target = make_user("user")
    target_cookie = sessions.issue_session(target.id, None, "pytest")

    r = admin_client.post(f"{BASE}/{target.id}/password", json={"password": NEW_PASSWORD})
    assert r.status_code == 204 and r.content == b""
    assert sessions.resolve_session(target_cookie) is None
    stored = users.get_user(target.id)
    assert stored.must_change_password is True

    login = lambda pw: anon_client.post(  # noqa: E731 - tiny local helper
        "/api/v1/auth/login", json={"email": target.email, "password": pw}, headers=CSRF_HEADERS
    )
    assert login(AUTH_TEST_PASSWORD).status_code == 401
    ok = login(NEW_PASSWORD)
    assert ok.status_code == 200 and ok.json()["user"]["must_change_password"] is True


@pytest.mark.parametrize("password", ["short", "x" * 129, "p" * 1025])
def test_reset_password_policy_is_422_and_changes_nothing(admin_client, make_user, password):
    target = make_user()
    before = users.get_user(target.id).password_hash
    assert admin_client.post(f"{BASE}/{target.id}/password", json={"password": password}).status_code == 422
    assert users.get_user(target.id).password_hash == before


def test_audit_records_target_and_actor_without_secrets(admin_client, make_user):
    target = make_user()
    admin_client.patch(f"{BASE}/{target.id}", json={"is_active": False})
    admin_client.patch(f"{BASE}/{target.id}", json={"is_active": True})
    admin_client.post(f"{BASE}/{target.id}/password", json={"password": NEW_PASSWORD})
    created = admin_client.post(BASE, json=create_body()).json()

    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, user_id, payload::text AS payload FROM platform.audit_log "
                "WHERE payload->>'target_user_id' = ANY(:ids)"
            ),
            {"ids": [target.id, created["id"]]},
        ).all()
    assert {r.action for r in rows} == {"user_disabled", "user_enabled", "user_password_reset", "user_created"}
    assert all(r.user_id == admin_client.auth_user.id for r in rows)
    assert all(NEW_PASSWORD not in r.payload and AUTH_TEST_PASSWORD not in r.payload for r in rows)
