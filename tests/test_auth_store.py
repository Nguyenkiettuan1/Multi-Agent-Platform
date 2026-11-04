"""Auth store (users, sessions, login throttle) against the dev platform DB.

Every row is keyed by a throwaway `pytest-au-<uuid>@example.test` email / ip and
removed in `finally`, so the suite leaves the DB as it found it.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine
from core.security import sessions, throttle, users
from core.security.tokens import sign, token_hash

PASSWORD = "correct horse battery"
SECRET = "test-secret-for-auth-store"


@pytest.fixture(autouse=True)
def _auth_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_secret_key", SECRET)


def _email() -> str:
    return f"pytest-au-{uuid.uuid4().hex}@example.test"


@contextmanager
def _created_user(**kwargs):
    email = kwargs.pop("email", None) or _email()
    user = users.create_user(
        email,
        kwargs.pop("display_name", "Test User"),
        kwargs.pop("role", "user"),
        kwargs.pop("password", PASSWORD),
        kwargs.pop("must_change_password", False),
    )
    try:
        yield user
    finally:
        with get_platform_engine().begin() as conn:
            # auth_sessions rows go with the user (ON DELETE CASCADE).
            conn.execute(text("DELETE FROM platform.users WHERE id = :id"), {"id": user.id})
            conn.execute(
                text("DELETE FROM platform.auth_login_attempts WHERE email_norm = :e"),
                {"e": user.email},
            )


def _exec(sql: str, **params):
    with get_platform_engine().begin() as conn:
        return conn.execute(text(sql), params)


# --- users -----------------------------------------------------------------


def test_normalize_email_strips_and_lowercases():
    assert users.normalize_email("  Foo.Bar@Example.TEST \n") == "foo.bar@example.test"


def test_create_user_stores_normalized_email_and_hash():
    raw = f"  PyTest-AU-{uuid.uuid4().hex}@Example.Test "
    with _created_user(email=raw, role="admin", must_change_password=True) as user:
        assert user.email == raw.strip().lower()
        assert user.role == "admin"
        assert user.must_change_password is True
        assert user.is_active is True
        assert user.auth_provider == "local"
        fetched = users.get_local_user_by_email(user.email)
        assert fetched is not None and fetched.id == user.id
        assert fetched.password_hash and fetched.password_hash != PASSWORD
        # The hash must never leak through repr (logs, assertion output).
        assert fetched.password_hash not in repr(fetched)
        assert users.get_user(user.id).email == user.email


def test_nfc_and_nfd_emails_are_the_same_account():
    import unicodedata

    nfc = f"pytest-au-{uuid.uuid4().hex}-\u00e9@example.test"  # composed e-acute
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert users.normalize_email(nfd) == users.normalize_email(nfc) == nfc
    with _created_user(email=nfd) as user:
        assert user.email == nfc
        assert users.get_local_user_by_email(users.normalize_email(nfc)).id == user.id
        with pytest.raises(users.UserExists):
            users.create_user(nfc, "Dup", "user", PASSWORD, False)


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_create_user_rejects_empty_email(blank):
    with pytest.raises(ValueError, match="email"):
        users.create_user(blank, "X", "user", PASSWORD, False)


def test_session_ttl_setting_is_bounded():
    from pydantic import ValidationError

    from config.settings import Settings

    for bad in (0, -1, 169):
        with pytest.raises(ValidationError):
            Settings(database_url="postgresql+psycopg://x/y", auth_session_ttl_hours=bad)
    assert Settings(database_url="postgresql+psycopg://x/y", auth_session_ttl_hours=168).auth_session_ttl_hours == 168


def test_create_user_duplicate_email_any_case_raises():
    with _created_user() as user, pytest.raises(users.UserExists):
        users.create_user(user.email.upper(), "Dup", "user", PASSWORD, False)


def test_create_user_rejects_weak_password_and_bad_role():
    email = _email()
    with pytest.raises(users.PasswordPolicyError) as exc:
        users.create_user(email, "X", "user", "short", False)
    assert exc.value.errors
    with pytest.raises(ValueError):
        users.create_user(email, "X", "superuser", PASSWORD, False)
    assert users.get_local_user_by_email(email) is None


def test_create_user_accepts_vietnamese_password():
    with _created_user(password="Mật khẩu rất dài ạ") as user:
        from core.security.passwords import verify_password

        assert verify_password(users.get_local_user_by_email(user.email).password_hash, "Mật khẩu rất dài ạ")


def test_get_user_unknown_returns_none():
    assert users.get_user(str(uuid.uuid4())) is None
    assert users.get_local_user_by_email(_email()) is None


def test_system_users_are_not_local_logins_and_not_listed():
    assert users.get_local_user_by_email("service@system.invalid") is None
    items, total = users.list_users(limit=100, offset=0)
    assert all(u.auth_provider == "local" for u in items)
    assert total >= len(items)
    assert users.SERVICE_USER_ID not in {u.id for u in items}
    assert users.LEGACY_USER_ID not in {u.id for u in items}


def test_list_users_pages():
    with _created_user() as a, _created_user() as b:
        items, total = users.list_users(limit=1, offset=0)
        assert len(items) == 1 and total >= 2
        everything, _ = users.list_users(limit=1000, offset=0)
        assert {a.id, b.id} <= {u.id for u in everything}


def test_set_active_only_touches_local_users():
    with _created_user() as user:
        assert users.set_active(user.id, False) is True
        assert users.get_user(user.id).is_active is False
        assert users.set_active(user.id, True) is True
        assert users.get_user(user.id).is_active is True
    # System users are never toggled, even by a direct id.
    assert users.set_active(users.SERVICE_USER_ID, False) is False
    assert users.get_user(users.SERVICE_USER_ID).is_active is True
    assert users.set_active(str(uuid.uuid4()), False) is False


def test_set_password_validates_and_sets_flag():
    from core.security.passwords import verify_password

    with _created_user() as user:
        with pytest.raises(users.PasswordPolicyError):
            users.set_password(user.id, "short", must_change=False)
        assert users.set_password(user.id, "another long passphrase", must_change=True) is True
        fetched = users.get_local_user_by_email(user.email)
        assert fetched.must_change_password is True
        assert verify_password(fetched.password_hash, "another long passphrase")
        assert not verify_password(fetched.password_hash, PASSWORD)
        # Password equal to the account's own email is rejected.
        with pytest.raises(users.PasswordPolicyError):
            users.set_password(user.id, user.email, must_change=False)
    assert users.set_password(str(uuid.uuid4()), PASSWORD, must_change=False) is False


def test_touch_last_login_and_count_active_admins():
    with _created_user(role="admin") as admin:
        assert admin.last_login_at is None
        users.touch_last_login(admin.id)
        assert users.get_user(admin.id).last_login_at is not None
        before = users.count_active_admins()
        users.set_active(admin.id, False)
        assert users.count_active_admins() == before - 1
    # The seeded 'service' admin is active but a system user: it must not count
    # as a login-able admin, so the count equals the local-only query.
    service = users.get_user(users.SERVICE_USER_ID)
    assert service.role == "admin" and service.is_active and service.auth_provider == "system"
    local_admins = _exec(
        "SELECT count(*) FROM platform.users WHERE role = 'admin' AND is_active AND auth_provider = 'local'"
    ).scalar_one()
    assert users.count_active_admins() == local_admins


# --- sessions --------------------------------------------------------------


def test_issue_and_resolve_session():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "203.0.113.7", "pytest-agent")
        resolved = sessions.resolve_session(cookie)
        assert resolved is not None
        assert resolved.user_id == user.id
        assert resolved.email == user.email
        assert resolved.role == "user"
        assert resolved.token_hash == token_hash(cookie.rpartition(".")[0])
        row = _exec(
            "SELECT ip, user_agent, expires_at > now() + interval '11 hours' AS ttl_ok, "
            "expires_at < now() + interval '13 hours' AS ttl_cap "
            "FROM platform.auth_sessions WHERE user_id = :u",
            u=user.id,
        ).one()
        assert (row.ip, row.user_agent, row.ttl_ok, row.ttl_cap) == ("203.0.113.7", "pytest-agent", True, True)


def test_session_stores_only_hash_and_truncates_metadata():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "x" * 200, "ua" * 500)
        token = cookie.rpartition(".")[0]
        rows = _exec("SELECT token_hash, ip, user_agent FROM platform.auth_sessions WHERE user_id = :u", u=user.id).all()
        assert len(rows) == 1
        assert rows[0].token_hash == token_hash(token) and token not in rows[0].token_hash
        assert len(rows[0].ip) == 64 and len(rows[0].user_agent) == 300


def test_issue_session_accepts_missing_metadata():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, None, None)
        assert sessions.resolve_session(cookie) is not None


def test_resolve_rejects_forged_or_garbage_cookie():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "1.2.3.4", "ua")
        assert sessions.resolve_session(cookie[:-1] + ("A" if cookie[-1] != "A" else "B")) is None
        assert sessions.resolve_session(cookie.rpartition(".")[0]) is None
        assert sessions.resolve_session("") is None
        # Valid token signed with another secret.
        assert sessions.resolve_session(sign(cookie.rpartition(".")[0], "other-secret")) is None


def test_resolve_rejects_system_user_session():
    # Defense in depth: a DB row for an active system user (the seeded 'service'
    # account) must not resolve to a cookie login.
    from core.security.tokens import new_token

    token = new_token()
    _exec(
        "INSERT INTO platform.auth_sessions (token_hash, user_id, expires_at) "
        "VALUES (:h, CAST(:u AS uuid), now() + interval '1 hour')",
        h=token_hash(token),
        u=users.SERVICE_USER_ID,
    )
    try:
        assert users.get_user(users.SERVICE_USER_ID).is_active
        assert sessions.resolve_session(sign(token, SECRET)) is None
    finally:
        _exec("DELETE FROM platform.auth_sessions WHERE token_hash = :h", h=token_hash(token))


def test_resolve_rejects_unknown_token():
    assert sessions.resolve_session(sign("never-issued-token", SECRET)) is None


def test_resolve_rejects_expired_session():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "1.2.3.4", "ua")
        _exec("UPDATE platform.auth_sessions SET expires_at = now() - interval '1 minute' WHERE user_id = :u", u=user.id)
        assert sessions.resolve_session(cookie) is None


def test_resolve_rejects_revoked_session():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "1.2.3.4", "ua")
        assert sessions.revoke_session(cookie) is True
        assert sessions.resolve_session(cookie) is None
        assert sessions.revoke_session(cookie) is False  # already revoked: idempotent
        assert sessions.revoke_session("garbage") is False


def test_resolve_rejects_deactivated_user():
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "1.2.3.4", "ua")
        users.set_active(user.id, False)
        assert sessions.resolve_session(cookie) is None
        users.set_active(user.id, True)
        assert sessions.resolve_session(cookie) is not None


def test_changing_secret_invalidates_sessions(monkeypatch):
    with _created_user() as user:
        cookie = sessions.issue_session(user.id, "1.2.3.4", "ua")
        monkeypatch.setattr(get_settings(), "auth_secret_key", "rotated-secret")
        assert sessions.resolve_session(cookie) is None


def test_revoke_all_for_user_keeps_except_hash():
    with _created_user() as user, _created_user() as other:
        keep = sessions.issue_session(user.id, "1.1.1.1", "a")
        drop1 = sessions.issue_session(user.id, "1.1.1.2", "b")
        drop2 = sessions.issue_session(user.id, "1.1.1.3", "c")
        other_cookie = sessions.issue_session(other.id, "1.1.1.4", "d")
        keep_hash = sessions.resolve_session(keep).token_hash

        assert sessions.revoke_all_for_user(user.id, except_hash=keep_hash) == 2
        assert sessions.resolve_session(keep) is not None
        assert sessions.resolve_session(drop1) is None
        assert sessions.resolve_session(drop2) is None
        assert sessions.resolve_session(other_cookie) is not None  # other users untouched

        assert sessions.revoke_all_for_user(user.id) == 1
        assert sessions.resolve_session(keep) is None


def test_issue_session_purges_only_own_expired_sessions():
    with _created_user() as user, _created_user() as other:
        sessions.issue_session(user.id, "1.1.1.1", "a")
        sessions.issue_session(other.id, "1.1.1.2", "b")
        _exec("UPDATE platform.auth_sessions SET expires_at = now() - interval '1 hour' WHERE user_id IN (:a, :b)", a=user.id, b=other.id)
        sessions.issue_session(user.id, "1.1.1.3", "c")
        count = lambda uid: _exec("SELECT count(*) FROM platform.auth_sessions WHERE user_id = :u", u=uid).scalar_one()
        assert count(user.id) == 1  # own expired row purged, new one kept
        assert count(other.id) == 1  # someone else's expired row is not touched


def test_missing_secret_fails_fast(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_secret_key", "")
    with _created_user() as user:
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY is not set"):
            sessions.issue_session(user.id, "1.1.1.1", "a")
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY is not set"):
            sessions.resolve_session("a.b")


# --- throttle --------------------------------------------------------------


@contextmanager
def _throttle_keys():
    email, ip = _email(), f"pytest-ip-{uuid.uuid4().hex[:12]}"
    try:
        yield email, ip
    finally:
        _exec("DELETE FROM platform.auth_login_attempts WHERE email_norm = :e OR ip LIKE :p", e=email, p=f"{ip}%")


def _begin(email: str, ip: str, n: int = 1):
    """n attempts that never get marked succeeded, i.e. n failed logins."""
    return [throttle.begin_login_attempt(email, ip) for _ in range(n)]


def _count(email: str) -> int:
    return _exec("SELECT count(*) FROM platform.auth_login_attempts WHERE email_norm = :e", e=email).scalar_one()


def _insert_attempt(email: str, ip: str, minutes_ago: int, succeeded: bool = False):
    _exec(
        "INSERT INTO platform.auth_login_attempts (email_norm, ip, succeeded, created_at) "
        "VALUES (:e, :i, :ok, now() - make_interval(mins => :m))",
        e=email,
        i=ip,
        ok=succeeded,
        m=minutes_ago,
    )


def test_throttle_allows_up_to_threshold_and_returns_attempt_ids():
    with _throttle_keys() as (email, ip):
        results = _begin(email, ip, 5)  # the 5th attempt is still allowed
        assert all(wait is None and isinstance(aid, int) for wait, aid in results)
        assert len({aid for _, aid in results}) == 5


def test_throttle_blocks_sixth_attempt_and_records_nothing():
    with _throttle_keys() as (email, ip):
        _begin(email, ip, 5)
        wait, aid = throttle.begin_login_attempt(email, ip)
        assert aid is None and wait is not None and 1 <= wait <= 15 * 60
        assert _count(email) == 5
        # Another IP is still blocked for the same email.
        assert throttle.begin_login_attempt(email, ip + "-other")[1] is None


def test_throttle_success_resets_email_counter():
    with _throttle_keys() as (email, ip):
        _begin(email, ip, 4)
        _, ok_id = throttle.begin_login_attempt(email, ip)
        throttle.mark_succeeded(ok_id)
        assert all(aid is not None for _, aid in _begin(email, ip, 5))
        assert throttle.begin_login_attempt(email, ip)[1] is None  # 5 fresh failures: blocked


def test_failure_during_owners_hashing_survives_mark_succeeded():
    with _throttle_keys() as (email, ip):
        _begin(email, ip, 3)
        _, attempt_a = throttle.begin_login_attempt(email, ip)  # pending, still hashing
        _begin(email, ip, 1)  # failure F lands after A began
        throttle.mark_succeeded(attempt_a)
        # F is later than A, so it still counts: F + 4 more failures reach the limit.
        assert all(aid is not None for _, aid in _begin(email, ip, 4))
        assert throttle.begin_login_attempt(email, ip)[1] is None


def test_throttle_success_does_not_count_against_ip():
    with _throttle_keys() as (_, ip):
        for _i in range(25):
            wait, aid = throttle.begin_login_attempt(_email(), ip)
            assert wait is None, "successful logins must not fill the IP counter"
            throttle.mark_succeeded(aid)


def test_throttle_ignores_failures_older_than_window():
    with _throttle_keys() as (email, ip):
        for _i in range(5):
            _insert_attempt(email, ip, 16)
        assert throttle.begin_login_attempt(email, ip)[0] is None


def test_throttle_retry_after_follows_fifth_newest_failure():
    with _throttle_keys() as (email, ip):
        for age in (14, 1, 1, 1, 1):  # the 14-minute-old one expires in ~1 minute
            _insert_attempt(email, ip, age)
        wait, aid = throttle.begin_login_attempt(email, ip)
        assert aid is None and 1 <= wait <= 61


def test_throttle_blocks_ip_after_twenty_failures_across_emails():
    with _throttle_keys() as (_, ip):
        for _i in range(20):
            assert throttle.begin_login_attempt(_email(), ip)[0] is None
        assert throttle.begin_login_attempt(_email(), ip)[0] is not None
        _exec("DELETE FROM platform.auth_login_attempts WHERE ip = :i", i=ip)


def test_throttle_treats_unknown_email_like_real_one():
    # No users row exists for this email, yet it is throttled all the same, so
    # the lock-out never reveals which accounts are real.
    with _throttle_keys() as (email, ip):
        assert users.get_local_user_by_email(email) is None
        _begin(email, ip, 5)
        assert throttle.begin_login_attempt(email, ip)[0] is not None


def test_throttle_handles_missing_ip_and_long_ip():
    email = _email()
    try:
        throttle.begin_login_attempt(email, None)
        throttle.begin_login_attempt(email, "z" * 300)
        rows = _exec("SELECT ip FROM platform.auth_login_attempts WHERE email_norm = :e", e=email).scalars().all()
        assert sorted(len(r) for r in rows) == [len(throttle.UNKNOWN_IP), 64]
    finally:
        _exec("DELETE FROM platform.auth_login_attempts WHERE email_norm = :e", e=email)


def test_begin_attempt_purges_old_rows_of_same_email_only():
    with _throttle_keys() as (email, ip):
        other = _email()
        try:
            for e in (email, other):
                _insert_attempt(e, ip, 2 * 24 * 60)
            throttle.begin_login_attempt(email, ip)
            assert _count(email) == 1
            assert _count(other) == 1
        finally:
            _exec("DELETE FROM platform.auth_login_attempts WHERE email_norm = :e", e=other)


def test_purge_old_attempts_deletes_only_expired_rows():
    with _throttle_keys() as (email, ip):
        _insert_attempt(email, ip, 2 * 24 * 60)
        _insert_attempt(email, ip, 5)
        assert throttle.purge_old_attempts() >= 1
        assert _count(email) == 1


def _run_concurrently(calls):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(lambda f: f(), calls))


def test_concurrent_attempts_for_one_email_pass_at_most_five():
    # Regression: check-then-record let all 40 of 40 concurrent logins through.
    with _throttle_keys() as (email, ip):
        results = _run_concurrently([lambda n=n: throttle.begin_login_attempt(email, f"{ip}-{n}") for n in range(40)])
        assert sum(1 for wait, _ in results if wait is None) == throttle.MAX_FAILURES_PER_EMAIL


def test_concurrent_attempts_from_one_ip_pass_at_most_twenty():
    with _throttle_keys() as (_, ip):
        results = _run_concurrently([lambda: throttle.begin_login_attempt(_email(), ip) for _ in range(40)])
        assert sum(1 for wait, _ in results if wait is None) == throttle.MAX_FAILURES_PER_IP
        _exec("DELETE FROM platform.auth_login_attempts WHERE ip = :i", i=ip)
