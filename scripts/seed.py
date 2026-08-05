"""Seed PostgreSQL app schema — run manually: python scripts/seed.py"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from config import get_settings


def seed() -> None:
    settings = get_settings()
    if not settings.migrate_database_url:
        raise RuntimeError("Set MIGRATE_DATABASE_URL in .env before running seed.")
    engine = create_engine(settings.migrate_database_url)

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app.contracts")).scalar()
        if count and count > 0:
            print(f"Database already seeded ({count} contracts).")
            return

        conn.execute(text("""
            INSERT INTO app.clients (id, name, tax_code, email) VALUES
            (1, 'ABC Corp', '0123456789', 'contact@abc.vn'),
            (2, 'XYZ Ltd', '0987654321', 'info@xyz.vn'),
            (3, 'DEF Inc', '0555666777', 'legal@def.vn')
            ON CONFLICT DO NOTHING
        """))

        conn.execute(text("""
            INSERT INTO app.contracts (code, client_id, title, status, value_vnd, signed_at, expires_at) VALUES
            ('HD-2024-001', 1, 'Hợp đồng tư vấn pháp lý ABC Corp', 'active', 500000000, '2024-01-15', '2025-01-14'),
            ('HD-2024-002', 2, 'Hợp đồng dịch vụ luật sư XYZ Ltd', 'active', 1200000000, '2024-03-01', '2026-02-28'),
            ('HD-2023-015', 3, 'Hợp đồng hết hạn DEF Inc', 'expired', 300000000, '2023-06-01', '2024-05-31')
        """))

        conn.commit()
        print("Seeded 3 clients and 3 contracts into PostgreSQL (app schema).")


if __name__ == "__main__":
    seed()
