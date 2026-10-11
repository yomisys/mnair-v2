"""
Migration Script: sponsors + payments (v2.1 monetisation)
(Windows Compatible, idempotent — safe to re-run)

What it does on an EXISTING database:
  1. organizations, sponsor_codes, sponsor_charges, payments
                                 tables created (via metadata.create_all)
  2. users                     += sponsor_code_id (FK, SET NULL), sponsored_at
  3. certificates              += access_type (default 'free' — every
                                  certificate issued so far stays a valid,
                                  verifiable credential), organization_id,
                                  sponsor_name

A brand-new database does not need this: init_db_simple.py creates
everything from the models.

Usage (from inside the backend container or a matching venv):
    python migrate_v3_sponsors.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from app.database import AsyncSessionLocal, engine, Base  # noqa: E402
import app.models  # noqa: E402,F401  -- registers every table incl. the sponsor tables


async def migrate():
    # New tables first: users.sponsor_code_id references sponsor_codes
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] organizations, sponsor_codes, sponsor_charges, payments present.")

    async with AsyncSessionLocal() as db:
        dialect = db.bind.dialect.name if db.bind is not None else engine.dialect.name

        if dialect == "postgresql":
            await db.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS sponsor_code_id INTEGER "
                "REFERENCES sponsor_codes(id) ON DELETE SET NULL"
            ))
            await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS sponsored_at TIMESTAMPTZ"))
            await db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_sponsor_code_id ON users (sponsor_code_id)"))
            await db.commit()
            print("[OK] users.sponsor_code_id and users.sponsored_at present.")

            await db.execute(text(
                "ALTER TABLE certificates ADD COLUMN IF NOT EXISTS access_type VARCHAR(20) NOT NULL DEFAULT 'free'"
            ))
            await db.execute(text(
                "ALTER TABLE certificates ADD COLUMN IF NOT EXISTS organization_id INTEGER "
                "REFERENCES organizations(id) ON DELETE SET NULL"
            ))
            await db.execute(text("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS sponsor_name VARCHAR(255)"))
            await db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_certificates_organization_id ON certificates (organization_id)"
            ))
            await db.commit()
            print("[OK] certificates.access_type, organization_id, sponsor_name present (existing rows = 'free').")
        else:
            print(f"[WARN] dialect '{dialect}' — column ALTERs skipped (only needed on PostgreSQL).")


async def main():
    try:
        await migrate()
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
