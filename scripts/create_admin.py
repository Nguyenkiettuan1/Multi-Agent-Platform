#!/usr/bin/env python3
"""Create the first local admin — run manually: python scripts/create_admin.py --email you@example.com

The password is never a command-line argument (it would land in shell history and the
process list). It comes from CREATE_ADMIN_PASSWORD if set (non-interactive provisioning),
otherwise it is prompted twice.

Exit codes: 0 created; 1 refused (invalid or existing email, weak password, mismatch, invalid name, DB problem);
2 usage error (argparse).
"""

import argparse
import getpass
import os
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy.exc import DBAPIError

from core.database.engines import platform_db_configured
from core.observability.audit import write_audit
from core.security.users import PasswordPolicyError, UserExists, create_user

PASSWORD_ENV = "CREATE_ADMIN_PASSWORD"


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def main(
    argv: list[str] | None = None,
    *,
    prompt: Callable[[str], str] = getpass.getpass,
    env: Mapping[str, str] = os.environ,
) -> int:
    parser = argparse.ArgumentParser(description="Create a local admin account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Admin", help="display name (default: Admin)")
    args = parser.parse_args(argv)

    if not platform_db_configured():
        return _fail("PLATFORM_DATABASE_URL is not set in .env; cannot reach the users table.")

    password = env.get(PASSWORD_ENV)
    if password:
        print(f"Using password from {PASSWORD_ENV}", file=sys.stderr)
    else:
        password = prompt("Password: ")
        if password != prompt("Confirm password: "):
            return _fail("passwords do not match.")

    # must_change_password=False: the operator just chose this password themselves,
    # so forcing an immediate change would only add a step.
    try:
        user = create_user(args.email, args.name, "admin", password, must_change_password=False)
    except PasswordPolicyError as exc:
        return _fail(str(exc))
    except UserExists:
        return _fail("an account with this email already exists; nothing was changed.")
    except ValueError as exc:
        return _fail(str(exc))
    except DBAPIError as exc:
        # Never print str(exc): SQLAlchemy appends the statement parameters, which hold the hash.
        return _fail(f"database error ({type(exc.orig).__name__}); nothing was created.")

    write_audit(
        trace_id=uuid.uuid4().hex,
        action="user_created",
        agent_name="cli",
        # The actor is the CLI, not the new user.
        payload={"target_user_id": user.id, "email": user.email, "role": user.role},
    )
    print(f"Created admin {user.email} (id {user.id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
