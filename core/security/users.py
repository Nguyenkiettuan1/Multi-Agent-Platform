"""User accounts in platform.users. Parameterised SQL only; no HTTP concerns."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text

from core.database.engines import get_platform_engine
from core.security.passwords import hash_password, validate_password

# Seeded by migration 010. Neither can log in (auth_provider = 'system').
LEGACY_USER_ID = "00000000-0000-0000-0000-000000000001"
SERVICE_USER_ID = "00000000-0000-0000-0000-000000000002"

ROLES = ("user", "admin")

_COLUMNS = (
    "id::text AS id, email, display_name, role, auth_provider, password_hash, "
    "is_active, must_change_password, created_at, last_login_at"
)


class UserExists(Exception):
    """The (case-insensitive) email is already registered."""


class PasswordPolicyError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: str
    auth_provider: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    # repr=False: keeps the hash out of logs and assertion diffs.
    password_hash: str | None = field(default=None, repr=False)


def normalize_email(raw: str) -> str:
    # NFC like passwords.py: a decomposed (NFD) email from some IMEs must resolve
    # to the same account as the composed one.
    return unicodedata.normalize("NFC", raw.strip()).lower()


EMAIL_MAX_LENGTH = 320  # platform.users.email VARCHAR(320)
DISPLAY_NAME_MAX_LENGTH = 200  # platform.users.display_name VARCHAR(200)


def validate_email(raw: str) -> str:
    """Normalised email, or ValueError.

    Deliberately basic (no RFC 5322): exactly one "@", no whitespace, non-empty
    local part, and a domain that has a dot or is "localhost". Real ownership is
    not checked here; this only keeps garbage and over-long values out of the DB.
    """
    email = normalize_email(raw)
    if not email:
        raise ValueError("email must not be empty")
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValueError(f"email must be at most {EMAIL_MAX_LENGTH} characters")
    local, sep, domain = email.partition("@")
    if (
        not sep
        or "@" in domain
        or not local
        or not domain
        or any(c.isspace() for c in email)
        or not ("." in domain or domain == "localhost")
    ):
        raise ValueError("email is not a valid address (expected name@domain.tld)")
    return email


def validate_display_name(name: str) -> None:
    # len() counts code points, matching how VARCHAR(n) counts characters.
    if len(name) > DISPLAY_NAME_MAX_LENGTH:
        raise ValueError(f"display name must be at most {DISPLAY_NAME_MAX_LENGTH} characters")


def _to_user(row) -> User:
    return User(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        role=row.role,
        auth_provider=row.auth_provider,
        is_active=row.is_active,
        must_change_password=row.must_change_password,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
        password_hash=row.password_hash,
    )


def create_user(
    email: str, display_name: str, role: str, password: str, must_change_password: bool
) -> User:
    # All checks run before hashing, so no failure after this point can carry the hash.
    email_norm = validate_email(email)
    validate_display_name(display_name)
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    errors = validate_password(password, email=email_norm)
    if errors:
        raise PasswordPolicyError(errors)
    # Hash outside the transaction: it is deliberately slow and must not hold a connection.
    password_hash = hash_password(password)
    with get_platform_engine().begin() as conn:
        row = conn.execute(
            text(
                f"""
                INSERT INTO platform.users
                    (email, display_name, role, auth_provider, password_hash, must_change_password)
                VALUES (:email, :name, :role, 'local', :hash, :must)
                ON CONFLICT DO NOTHING
                RETURNING {_COLUMNS}
                """
            ),
            {
                "email": email_norm,
                "name": display_name,
                "role": role,
                "hash": password_hash,
                "must": must_change_password,
            },
        ).first()
    if row is None:
        raise UserExists(email_norm)
    return _to_user(row)


def get_local_user_by_email(email_norm: str) -> User | None:
    """Login lookup; system users have no password and never match."""
    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLUMNS} FROM platform.users WHERE lower(email) = :e AND auth_provider = 'local'"),
            {"e": email_norm},
        ).first()
    return _to_user(row) if row else None


def get_user(user_id: str) -> User | None:
    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT {_COLUMNS} FROM platform.users WHERE id = CAST(:id AS uuid)"),
            {"id": user_id},
        ).first()
    return _to_user(row) if row else None


def list_users(limit: int, offset: int) -> tuple[list[User], int]:
    """Local accounts only (system users are hidden), plus the total for paging."""
    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {_COLUMNS} FROM platform.users
                WHERE auth_provider <> 'system'
                ORDER BY created_at, id
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        ).all()
        total = conn.execute(
            text("SELECT count(*) FROM platform.users WHERE auth_provider <> 'system'")
        ).scalar_one()
    return [_to_user(r) for r in rows], total


def set_active(user_id: str, active: bool) -> bool:
    """False if no such local user. System users are never touched."""
    with get_platform_engine().begin() as conn:
        result = conn.execute(
            text(
                "UPDATE platform.users SET is_active = :active, updated_at = now() "
                "WHERE id = CAST(:id AS uuid) AND auth_provider = 'local'"
            ),
            {"id": user_id, "active": active},
        )
    return result.rowcount > 0


def set_password(user_id: str, password: str, must_change: bool) -> bool:
    """Validate against the account's own email, then store the new hash.

    Does not revoke sessions: the caller decides which ones survive.
    """
    user = get_user(user_id)
    if user is None or user.auth_provider != "local":
        return False
    errors = validate_password(password, email=user.email)
    if errors:
        raise PasswordPolicyError(errors)
    password_hash = hash_password(password)
    with get_platform_engine().begin() as conn:
        result = conn.execute(
            text(
                "UPDATE platform.users SET password_hash = :hash, must_change_password = :must, "
                "updated_at = now() WHERE id = CAST(:id AS uuid) AND auth_provider = 'local'"
            ),
            {"id": user_id, "hash": password_hash, "must": must_change},
        )
    return result.rowcount > 0


def count_active_admins() -> int:
    """Admins who can actually log in (the 'service' system admin does not count)."""
    with get_platform_engine().connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM platform.users "
                "WHERE role = 'admin' AND is_active AND auth_provider = 'local'"
            )
        ).scalar_one()


def touch_last_login(user_id: str) -> None:
    with get_platform_engine().begin() as conn:
        conn.execute(
            text("UPDATE platform.users SET last_login_at = now() WHERE id = CAST(:id AS uuid)"),
            {"id": user_id},
        )
