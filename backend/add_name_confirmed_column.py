"""
Migration Script: Add name_confirmed column + AWAITING_CERTIFICATE_NAME enum
value (Windows Compatible)

Base.metadata.create_all only creates missing TABLES, it never ALTERs an
existing table's columns or an existing Postgres ENUM type's values -- so
both of these need a one-off migration like this rather than a container
restart. Without the enum fix, the app crashes the first time it tries to
write ConversationState.AWAITING_CERTIFICATE_NAME to the database (Postgres
rejects the unrecognized label).

Every existing learner currently holds the auto-assigned "WhatsApp User" /
"USSD User NNNN" placeholder, never a real name they provided -- so
name_confirmed=False is the correct value for 100% of existing rows.
Idempotent: uses IF NOT EXISTS, safe to re-run.

Usage (from inside the backend container or a matching venv):
    python add_name_confirmed_column.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal


async def migrate():
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "name_confirmed BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await db.commit()
        print("[OK] users.name_confirmed column present (added or already existed).")

        # Postgres ENUM types need their own ALTER TYPE to add a value --
        # the Python model change alone only affects newly-created databases.
        # Postgres 12+ allows ADD VALUE inside a normal transaction as long
        # as the new value isn't used by another statement in that same
        # transaction, which is the case here.
        await db.execute(text(
            "ALTER TYPE conversationstate ADD VALUE IF NOT EXISTS "
            "'AWAITING_CERTIFICATE_NAME'"
        ))
        await db.commit()
        print("[OK] conversationstate enum has AWAITING_CERTIFICATE_NAME (added or already existed).")

        result = await db.execute(text(
            "SELECT count(*) FILTER (WHERE name_confirmed = TRUE), count(*) FROM users"
        ))
        confirmed, total = result.one()
        print(f"Current state: {confirmed}/{total} users have a confirmed (real) name.")


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
