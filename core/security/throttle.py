"""Login throttling backed by platform.auth_login_attempts.

Login flow (MA-AU-T7):
    wait, attempt_id = begin_login_attempt(email_norm, ip)
    if wait: answer 429 with Retry-After; do no hashing (and nothing was recorded)
    verify the password ...
    if correct: mark_succeeded(attempt_id)

The attempt is recorded as a failure BEFORE the slow password check, in the same
transaction as the limit check and under advisory locks. Check-then-record as
two separate steps let N concurrent requests all pass the check before any of
them recorded (40 of 40 got through a limit of 5). Unknown emails take the
exact same path, so the lock-out reveals nothing about which accounts exist.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from core.database.engines import get_platform_engine

MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20
WINDOW_MINUTES = 15
RETENTION_DAYS = 1

# auth_login_attempts.ip is NOT NULL and VARCHAR(64).
UNKNOWN_IP = "unknown"
_IP_MAX = 64

# Advisory-lock namespaces. Every transaction takes the email lock first and the
# IP lock second, so lock order is the same everywhere and cannot deadlock.
_LOCK_EMAIL = 7301
_LOCK_IP = 7302

_EMAIL_REMAINING = text(
    """
    SELECT created_at + make_interval(mins => :window) - now() AS remaining
    FROM platform.auth_login_attempts
    WHERE email_norm = :e AND NOT succeeded
      AND created_at > now() - make_interval(mins => :window)
      AND created_at > COALESCE(
          (SELECT max(created_at) FROM platform.auth_login_attempts
           WHERE email_norm = :e AND succeeded), '-infinity'::timestamptz)
    ORDER BY created_at DESC
    OFFSET :skip LIMIT 1
    """
)
# A row flipped by mark_succeeded no longer matches NOT succeeded, so successful
# logins never count against the IP.
_IP_REMAINING = text(
    """
    SELECT created_at + make_interval(mins => :window) - now() AS remaining
    FROM platform.auth_login_attempts
    WHERE ip = :i AND NOT succeeded
      AND created_at > now() - make_interval(mins => :window)
    ORDER BY created_at DESC
    OFFSET :skip LIMIT 1
    """
)


def _ip(ip: str | None) -> str:
    return (ip or UNKNOWN_IP)[:_IP_MAX]


def _wait_seconds(conn: Connection, email_norm: str, ip: str) -> int | None:
    # The lock lifts when the Nth-newest counted failure leaves the window, so
    # that row (OFFSET N-1) tells us how long is left, if at least N exist.
    waits: list[int] = []
    for sql, key, limit in (
        (_EMAIL_REMAINING, {"e": email_norm}, MAX_FAILURES_PER_EMAIL),
        (_IP_REMAINING, {"i": ip}, MAX_FAILURES_PER_IP),
    ):
        row = conn.execute(sql, {**key, "window": WINDOW_MINUTES, "skip": limit - 1}).first()
        if row is not None:
            waits.append(max(1, int(row.remaining.total_seconds()) + 1))
    return max(waits) if waits else None


def begin_login_attempt(email_norm: str, ip: str | None) -> tuple[int | None, int | None]:
    """Atomically check the limits and, if allowed, record a pending failure.

    Returns (wait_seconds, None) when blocked (nothing recorded, so blocked
    requests do not extend the lock-out), else (None, attempt_id).
    """
    ip = _ip(ip)
    with get_platform_engine().begin() as conn:
        lock = text("SELECT pg_advisory_xact_lock(:ns, hashtext(:v))")
        conn.execute(lock, {"ns": _LOCK_EMAIL, "v": email_norm})
        conn.execute(lock, {"ns": _LOCK_IP, "v": ip})
        wait = _wait_seconds(conn, email_norm, ip)
        if wait is not None:
            return wait, None
        attempt_id = conn.execute(
            text(
                "INSERT INTO platform.auth_login_attempts (email_norm, ip, succeeded) "
                "VALUES (:e, :i, FALSE) RETURNING id"
            ),
            {"e": email_norm, "i": ip},
        ).scalar_one()
        # Housekeeping scoped to this email keeps the write cheap (indexed); the
        # global sweep is purge_old_attempts().
        conn.execute(
            text(
                "DELETE FROM platform.auth_login_attempts "
                "WHERE email_norm = :e AND created_at < now() - make_interval(days => :days)"
            ),
            {"e": email_norm, "days": RETENTION_DAYS},
        )
    return None, attempt_id


def mark_succeeded(attempt_id: int) -> None:
    """Flip a pending attempt to success after the password was verified.

    created_at is left alone on purpose: failures that landed while this
    request was hashing are later than the success and keep counting.
    """
    with get_platform_engine().begin() as conn:
        conn.execute(
            text("UPDATE platform.auth_login_attempts SET succeeded = TRUE WHERE id = :id"),
            {"id": attempt_id},
        )


def purge_old_attempts() -> int:
    """Delete attempts past retention, for every email (lifespan / periodic use)."""
    with get_platform_engine().begin() as conn:
        return conn.execute(
            text("DELETE FROM platform.auth_login_attempts WHERE created_at < now() - make_interval(days => :days)"),
            {"days": RETENTION_DAYS},
        ).rowcount
