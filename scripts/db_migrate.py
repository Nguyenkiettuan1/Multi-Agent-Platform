#!/usr/bin/env python3
"""Run database migrations — chỉ chạy thủ công: python scripts/db_migrate.py"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from config import get_settings

MIGRATIONS_DIR = _ROOT / "infra" / "database" / "migrations"


def run_migrations() -> None:
    settings = get_settings()
    if not settings.migrate_database_url:
        raise RuntimeError("Set MIGRATE_DATABASE_URL in .env before running migrations.")
    engine = create_engine(settings.migrate_database_url)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not migration_files:
        print("No migration files found.")
        sys.exit(1)

    with engine.connect() as conn:
        for path in migration_files:
            print(f"Running {path.name}...")
            sql = path.read_text(encoding="utf-8")
            conn.execute(text(sql))
            conn.commit()

    print(f"Done — {len(migration_files)} migrations applied.")


if __name__ == "__main__":
    run_migrations()
