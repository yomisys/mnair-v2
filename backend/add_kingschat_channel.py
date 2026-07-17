"""
Migration Script: Add 'kingschat' value to the conversationchannel enum
(Windows Compatible)

Base.metadata.create_all only creates missing TABLES, it never ALTERs an
existing Postgres ENUM type's values -- so this needs a one-off migration
like add_name_confirmed_column.py rather than a container restart. Without
this, the app crashes the first time it tries to write
ConversationChannel.KINGSCHAT to the database (Postgres rejects the
unrecognized label).

Idempotent: uses IF NOT EXISTS, safe to re-run.

Usage (from inside the backend container or a matching venv):
    python add_kingschat_channel.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal


async def migrate():
    async with AsyncSessionLocal() as db:
        # Postgres ENUM types need their own ALTER TYPE to add a value --
        # the Python model change alone (ConversationChannel.KINGSCHAT in
        # app/models/conversation.py) only affects newly-created databases.
        # Postgres 12+ allows ADD VALUE inside a normal transaction as long
        # as the new value isn't used by another statement in that same
        # transaction, which is the case here.
        await db.execute(text(
            "ALTER TYPE conversationchannel ADD VALUE IF NOT EXISTS "
            "'KINGSCHAT'"
        ))
        await db.commit()
        print("[OK] conversationchannel enum has KINGSCHAT (added or already existed).")


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
