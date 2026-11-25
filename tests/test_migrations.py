"""Migration 010 against a throwaway database (needs a role that can CREATE DATABASE)."""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from config import get_settings  # noqa: E402
from db_migrate import MIGRATIONS_DIR, run_migrations  # noqa: E402

ROLLBACK = _ROOT / "infra" / "database" / "rollback" / "010_auth_chat_history.down.sql"
LEGACY_ID = "00000000-0000-0000-0000-000000000001"
SERVICE_ID = "00000000-0000-0000-0000-000000000002"
NEW_TABLES = {"users", "auth_sessions", "auth_login_attempts", "chat_sessions", "chat_messages"}

T0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 1, 1, 8, 5, tzinfo=timezone.utc)
T2 = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def temp_db_url():
    admin_url = get_settings().migrate_database_url
    if not admin_url:
        pytest.skip("MIGRATE_DATABASE_URL not configured; cannot create a throwaway database")
    name = f"ma_mig_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except (OperationalError, ProgrammingError) as exc:
        admin.dispose()
        pytest.fail(f"migrate role cannot create a test database: {exc}")
    try:
        yield make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _apply(engine, files):
    with engine.connect() as conn:
        for path in files:
            conn.execute(text(path.read_text(encoding="utf-8")))
            conn.commit()


def _insert_feedback(engine, rows):
    with engine.begin() as conn:
        for trace_id, session_id, user_message, response, created_at in rows:
            conn.execute(
                text(
                    "INSERT INTO platform.feedback (trace_id, session_id, user_message, response, created_at) "
                    "VALUES (:t, :s, :u, :r, :c)"
                ),
                {"t": trace_id, "s": session_id, "u": user_message, "r": response, "c": created_at},
            )


def _scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def _new_tables(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'platform'")
        ).scalars()
        return NEW_TABLES & set(rows)


def test_migration_010_backfill_rerun_and_rollback(temp_db_url):
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    before_010 = [p for p in files if p.name < "010"]
    assert files[-1].name == "010_auth_chat_history.sql"

    engine = create_engine(temp_db_url)
    try:
        _apply(engine, before_010)
        # Row order in the table (id) deliberately disagrees with created_at: t-a2 has a larger id
        # but is older, t-a3/t-a4 share created_at, and sess-b has a fully NULL turn.
        _insert_feedback(
            engine,
            [
                ("t-a1", "sess-a", "Cảm ơn bạn", "Rất vui được giúp đỡ!", T1),
                ("t-a2", "sess-a", "Xin chào, hợp đồng này còn hiệu lực không?", "Còn hiệu lực đến năm 2027.", T0),
                ("t-a3", "sess-a", "Điều khoản thanh toán là gì?", "Thanh toán trong 30 ngày.", T2),
                ("t-a4", "sess-a", "Phạt vi phạm bao nhiêu?", "Tối đa 8% giá trị hợp đồng.", T2),
                ("t-b1", "sess-b", None, None, None),
                ("t-empty", "", "no session", "ignored", T0),
                ("t-nosess", None, "no session", "ignored", T0),
            ],
        )

        _apply(engine, [files[-1]])

        assert _scalar(engine, "SELECT count(*) FROM platform.chat_sessions") == 2
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_messages") == 10
        assert _scalar(engine, f"SELECT count(*) FROM platform.chat_sessions WHERE owner_id = '{LEGACY_ID}'") == 2
        assert _scalar(engine, f"SELECT is_active FROM platform.users WHERE id = '{LEGACY_ID}'") is False
        assert _scalar(engine, f"SELECT role FROM platform.users WHERE id = '{SERVICE_ID}'") == "admin"
        assert _scalar(
            engine, "SELECT count(*) FROM platform.users WHERE auth_provider = 'system' AND password_hash IS NULL"
        ) == 2
        # Title comes from the chronologically first user message, not the lowest id.
        assert _scalar(
            engine, "SELECT title FROM platform.chat_sessions WHERE id = 'sess-a'"
        ) == "Xin chào, hợp đồng này còn hiệu lực không?"
        with engine.connect() as conn:
            span = conn.execute(
                text("SELECT created_at, updated_at FROM platform.chat_sessions WHERE id = 'sess-a'")
            ).one()
        assert (span[0], span[1]) == (T0, T2)
        with engine.connect() as conn:
            msgs = conn.execute(
                text("SELECT session_id, role, content FROM platform.chat_messages ORDER BY id")
            ).all()
        assert msgs == [
            ("sess-b", "user", ""),
            ("sess-b", "assistant", ""),
            ("sess-a", "user", "Xin chào, hợp đồng này còn hiệu lực không?"),
            ("sess-a", "assistant", "Còn hiệu lực đến năm 2027."),
            ("sess-a", "user", "Cảm ơn bạn"),
            ("sess-a", "assistant", "Rất vui được giúp đỡ!"),
            ("sess-a", "user", "Điều khoản thanh toán là gì?"),
            ("sess-a", "assistant", "Thanh toán trong 30 ngày."),
            ("sess-a", "user", "Phạt vi phạm bao nhiêu?"),
            ("sess-a", "assistant", "Tối đa 8% giá trị hợp đồng."),
        ]

        # Full replay through the real entry point: no error, no duplicates.
        run_migrations(temp_db_url)
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_sessions") == 2
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_messages") == 10
        assert _scalar(engine, "SELECT count(*) FROM platform.users") == 2

        # Feedback written after the first apply must not be adopted by 'legacy'.
        _insert_feedback(engine, [("t-late", "sess-late", "Câu hỏi mới", "Trả lời mới", T2)])
        run_migrations(temp_db_url)
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_sessions") == 2
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_messages") == 10

        # The same (trace, role) cannot be stored twice.
        with pytest.raises(IntegrityError, match="ux_chat_messages_trace_role"):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO platform.chat_messages (session_id, role, trace_id) "
                        "VALUES ('sess-a', 'user', 't-a1')"
                    )
                )

        assert _new_tables(engine) == NEW_TABLES
        feedback_before = _scalar(engine, "SELECT count(*) FROM platform.feedback")
        with engine.connect() as conn:
            conn.exec_driver_sql(ROLLBACK.read_text(encoding="utf-8"))
            conn.commit()
        assert _new_tables(engine) == set()
        assert _scalar(engine, "SELECT count(*) FROM platform.feedback") == feedback_before == 8

        # Re-applying after a rollback re-runs the backfill (legacy is gone), adopting t-late too.
        run_migrations(temp_db_url)
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_sessions") == 3
        assert _scalar(engine, "SELECT count(*) FROM platform.chat_messages") == 12
    finally:
        engine.dispose()
