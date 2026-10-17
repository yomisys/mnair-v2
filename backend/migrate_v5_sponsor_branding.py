"""
Migration Script: sponsor white-label branding + advert (v2.3)
(Windows Compatible, idempotent — safe to re-run)

What it does on an EXISTING database:
  1. organizations += brand_color, tagline, welcome_message, website_url,
                      ad_enabled, ad_headline, ad_body, ad_cta_label,
                      ad_cta_url, ad_image_object, ad_suspended

Works on PostgreSQL and on the local SQLite file. A brand-new database does
not need this script.

Usage (from inside the backend container or a matching venv):
    python migrate_v5_sponsor_branding.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from app.database import engine  # noqa: E402
import app.models  # noqa: E402,F401

# name -> (PostgreSQL type, SQLite type)
COLUMNS = {
    "brand_color": ("VARCHAR(7)", "VARCHAR(7)"),
    "tagline": ("VARCHAR(160)", "VARCHAR(160)"),
    "welcome_message": ("TEXT", "TEXT"),
    "website_url": ("VARCHAR(500)", "VARCHAR(500)"),
    "ad_enabled": ("BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT 0"),
    "ad_headline": ("VARCHAR(120)", "VARCHAR(120)"),
    "ad_body": ("TEXT", "TEXT"),
    "ad_cta_label": ("VARCHAR(40)", "VARCHAR(40)"),
    "ad_cta_url": ("VARCHAR(500)", "VARCHAR(500)"),
    "ad_image_object": ("VARCHAR(255)", "VARCHAR(255)"),
    "ad_suspended": ("BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT 0"),
}


async def migrate():
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            for name, (pg_type, _) in COLUMNS.items():
                await conn.execute(text(f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {name} {pg_type}"))
        elif dialect == "sqlite":
            existing = {row[1] for row in (await conn.execute(text("PRAGMA table_info(organizations)"))).all()}
            for name, (_, sqlite_type) in COLUMNS.items():
                if name not in existing:
                    await conn.execute(text(f"ALTER TABLE organizations ADD COLUMN {name} {sqlite_type}"))
        else:
            print(f"[WARN] dialect '{dialect}' not handled — add the columns by hand.")
            return
    print("[OK] organizations branding + advert columns present.")
    await engine.dispose()


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
