"""scripts/create_admin.py against the dev platform DB.

main() takes the prompt function and environment as arguments, so no test touches a
real terminal. Rows use throwaway `pytest-au-<uuid>@example.test` emails and are
removed in `finally`.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from core.database.engines import get_platform_engine
from core.security import users
from core.security.passwords import verify_password

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import create_admin  # noqa: E402

PASSWORD = "Mật khẩu rất dài 2026"


def _email() -> str:
    return f"pytest-au-{uuid.uuid4().hex}@example.test"


def _prompts(*answers: str):
    queue = list(answers)
    return lambda _prompt: queue.pop(0)


def _cleanup(email: str) -> None:
    with get_platform_engine().begin() as conn:
        conn.execute(text("DELETE FROM platform.audit_log WHERE payload->>'email' = :e"), {"e": email})
        conn.execute(text("DELETE FROM platform.users WHERE lower(email) = :e"), {"e": email})


def _run(argv, *answers, env=None):
    return create_admin.main(argv, prompt=_prompts(*answers), env=env or {})


def test_creates_local_admin_without_forced_password_change(capsys):
    email = _email()
    try:
        code = _run(["--email", email, "--name", "Quản trị viên"], PASSWORD, PASSWORD)
        user = users.get_local_user_by_email(email)
        assert code == 0
        assert user is not None
        assert (user.role, user.auth_provider, user.display_name) == ("admin", "local", "Quản trị viên")
        assert user.must_change_password is False
        assert verify_password(user.password_hash, PASSWORD)
        assert user.id in capsys.readouterr().out
    finally:
        _cleanup(email)


def test_password_from_env_skips_prompt():
    email = _email()

    def no_prompt(_):
        raise AssertionError("must not prompt when CREATE_ADMIN_PASSWORD is set")

    try:
        code = create_admin.main(
            ["--email", email], prompt=no_prompt, env={"CREATE_ADMIN_PASSWORD": PASSWORD}
        )
        assert code == 0
        assert users.get_local_user_by_email(email) is not None
    finally:
        _cleanup(email)


def test_duplicate_email_refused_case_insensitively(capsys):
    email = _email()
    try:
        assert _run(["--email", email], PASSWORD, PASSWORD) == 0
        capsys.readouterr()
        code = _run(["--email", email.upper()], "Another long password 1", "Another long password 1")
        assert code == 1
        assert "already exists" in capsys.readouterr().err
        # The original account is untouched.
        assert verify_password(users.get_local_user_by_email(email).password_hash, PASSWORD)
    finally:
        _cleanup(email)


def test_weak_password_refused(capsys):
    email = _email()
    try:
        code = _run(["--email", email], "short", "short")
        assert code == 1
        assert "at least 12" in capsys.readouterr().err
        assert users.get_local_user_by_email(email) is None
    finally:
        _cleanup(email)


def test_mismatched_confirmation_refused(capsys):
    email = _email()
    try:
        code = _run(["--email", email], PASSWORD, PASSWORD + "x")
        assert code == 1
        assert "do not match" in capsys.readouterr().err
        assert users.get_local_user_by_email(email) is None
    finally:
        _cleanup(email)


def test_blank_email_refused(capsys):
    assert _run(["--email", "   "], PASSWORD, PASSWORD) == 1
    assert "email" in capsys.readouterr().err


def test_password_never_printed(capsys):
    email = _email()
    try:
        _run(["--email", email], PASSWORD, PASSWORD)
        _run(["--email", email], PASSWORD, PASSWORD)  # duplicate path
        _run(["--email", _email()], PASSWORD, PASSWORD + "x")  # mismatch path
        _run(["--email", _email()], PASSWORD[:5], PASSWORD[:5])  # policy path
        captured = capsys.readouterr()
        assert PASSWORD not in captured.out + captured.err
        assert PASSWORD[:5] not in captured.out + captured.err
    finally:
        _cleanup(email)


def test_audit_row_has_no_password():
    email = _email()
    try:
        _run(["--email", email], PASSWORD, PASSWORD)
        with get_platform_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT agent_name, user_id, payload::text AS payload FROM platform.audit_log "
                    "WHERE action = 'user_created' AND payload->>'email' = :e"
                ),
                {"e": email},
            ).one()
        assert row.agent_name == "cli"
        assert row.user_id is None
        assert f'"target_user_id": "{users.get_local_user_by_email(email).id}"' in row.payload
        assert PASSWORD not in row.payload
    finally:
        _cleanup(email)


def test_env_password_is_announced_on_stderr_without_its_value(capsys):
    email = _email()
    try:
        create_admin.main(["--email", email], prompt=_prompts(), env={"CREATE_ADMIN_PASSWORD": PASSWORD})
        err = capsys.readouterr().err
        assert "Using password from CREATE_ADMIN_PASSWORD" in err
        assert PASSWORD not in err
    finally:
        _cleanup(email)


def test_empty_env_password_falls_back_to_prompt():
    email = _email()
    try:
        code = _run(["--email", email], PASSWORD, PASSWORD, env={"CREATE_ADMIN_PASSWORD": ""})
        assert code == 0
        assert verify_password(users.get_local_user_by_email(email).password_hash, PASSWORD)
    finally:
        _cleanup(email)


def test_weak_password_from_env_refused(capsys):
    email = _email()
    try:
        code = _run(["--email", email], env={"CREATE_ADMIN_PASSWORD": "short"})
        assert code == 1
        assert "at least 12" in capsys.readouterr().err
        assert users.get_local_user_by_email(email) is None
    finally:
        _cleanup(email)


@pytest.mark.parametrize(
    "argv",
    [["--email", "not-an-email"], ["--email", _email(), "--name", "x" * 201], ["--email", "x" * 320 + "@a.test"]],
)
def test_invalid_email_or_name_refused_cleanly_without_hash(argv, capsys):
    assert _run(argv, PASSWORD, PASSWORD) == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "$argon2" not in captured.out + captured.err


def test_db_error_is_reported_without_parameters(monkeypatch, capsys):
    from sqlalchemy.exc import DataError

    def fail(*_a, **_k):
        raise DataError("INSERT ...", {"hash": "$argon2id$secret"}, Exception("too long"))

    monkeypatch.setattr(create_admin, "create_user", fail)
    assert _run(["--email", _email()], PASSWORD, PASSWORD) == 1
    err = capsys.readouterr().err
    assert "database error" in err
    assert "argon2" not in err


def test_refuses_before_prompting_when_platform_db_not_configured(monkeypatch, capsys):
    monkeypatch.setattr(create_admin, "platform_db_configured", lambda: False)

    def no_prompt(_):
        raise AssertionError("must not prompt")

    assert create_admin.main(["--email", _email()], prompt=no_prompt, env={}) == 1
    assert "PLATFORM_DATABASE_URL" in capsys.readouterr().err


def test_missing_email_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        _run([], PASSWORD, PASSWORD)
    assert exc.value.code == 2
