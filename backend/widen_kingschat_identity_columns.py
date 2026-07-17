"""
Migration Script: Widen phone_number/learner_phone columns from
VARCHAR(15) to VARCHAR(64) (Windows Compatible)

Base.metadata.create_all only creates missing TABLES, it never ALTERs an
existing table's column type -- so this needs a one-off migration like
add_kingschat_channel.py / add_name_confirmed_column.py rather than a
container restart.

Why: users.phone_number, conversations.phone_number, and
certificates.learner_phone all held Nigerian phone numbers (<=15 chars)
until the KingsChat channel started writing 'kc:{conversation_id}' into the
same slot (see app.channels.kingschat's identity-mapping docstring).
Confirmed live 2026-07-17 during the first real KingsChat test: real
conversation IDs run ~49 chars (e.g.
'53b9877a73322e5105030100_6a0ae2c1095c473320cb9891'), and the 'kc:' prefix
pushes it to ~52 -- both past VARCHAR(15). Postgres rejected every write
attempt outright (StringDataRightTruncationError), so every KingsChat
learner's very first message would have failed before this fix. This was
caught before any real learner hit it, but a database from before this
migration would still have the old, too-narrow column.

Idempotent: ALTER COLUMN TYPE to a wider VARCHAR is safe to re-run (no-op
if already VARCHAR(64) or wider).

Usage (from inside the backend container or a matching venv):
    python widen_kingschat_identity_columns.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal


async def migrate():
    async with AsyncSessionLocal() as db:
        await db.execute(text("ALTER TABLE users ALTER COLUMN phone_number TYPE VARCHAR(64)"))
        await db.execute(text("ALTER TABLE conversations ALTER COLUMN phone_number TYPE VARCHAR(64)"))
        await db.execute(text("ALTER TABLE certificates ALTER COLUMN learner_phone TYPE VARCHAR(64)"))
        await db.commit()
        print("[OK] users.phone_number, conversations.phone_number, "
              "certificates.learner_phone are now VARCHAR(64).")


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
