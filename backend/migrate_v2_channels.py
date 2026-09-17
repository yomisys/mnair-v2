"""
Migration Script: WhatsApp-free channels (v2)
(Windows Compatible, idempotent — safe to re-run)

What it does on an EXISTING database:
  1. conversationchannel enum  += 'TELEGRAM', 'WEB'
  2. users                     += telegram_chat_id, learner_pin_hash
  3. push_subscriptions        table created (via metadata.create_all)
  4. users.preferred_channel   'whatsapp' -> NULL (those learners must come
                                back through Telegram or the web app; the
                                nudge task only targets telegram/web)

A brand-new database does not need this: init_db_simple.py creates
everything from the models.

Usage (from inside the backend container or a matching venv):
    python migrate_v2_channels.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from app.database import AsyncSessionLocal, engine, Base  # noqa: E402
import app.models  # noqa: E402,F401  -- registers every table incl. push_subscriptions


async def migrate():
    async with AsyncSessionLocal() as db:
        dialect = db.bind.dialect.name if db.bind is not None else engine.dialect.name

        if dialect == "postgresql":
            # SQLAlchemy stores enum *names* in the Postgres type (KINGSCHAT
            # precedent in add_kingschat_channel.py).
            for value in ("TELEGRAM", "WEB"):
                await db.execute(text(f"ALTER TYPE conversationchannel ADD VALUE IF NOT EXISTS '{value}'"))
            await db.commit()
            print("[OK] conversationchannel enum has TELEGRAM and WEB.")

            await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(32)"))
            await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS learner_pin_hash VARCHAR(255)"))
            await db.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_chat_id ON users (telegram_chat_id)"
            ))
            await db.commit()
            print("[OK] users.telegram_chat_id and users.learner_pin_hash present.")

            result = await db.execute(text(
                "UPDATE users SET preferred_channel = NULL WHERE preferred_channel = 'whatsapp'"
            ))
            await db.commit()
            print(f"[OK] {result.rowcount} former WhatsApp learner(s) unassigned from a channel.")
        else:
            print(f"[WARN] dialect '{dialect}' — enum/column ALTERs skipped (only needed on PostgreSQL).")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] push_subscriptions table present.")


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
