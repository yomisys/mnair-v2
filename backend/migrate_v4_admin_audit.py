"""
Migration Script: admin audit log (v2.2 admin back office)
(Windows Compatible, idempotent — safe to re-run)

What it does on an EXISTING database:
  1. admin_audit_logs table created (via metadata.create_all)

No column changes: payments.status is a plain string, so the new 'voided'
status needs nothing. A brand-new database does not need this script.

Usage (from inside the backend container or a matching venv):
    python migrate_v4_admin_audit.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  -- registers every table incl. admin_audit_logs


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] admin_audit_logs present.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
