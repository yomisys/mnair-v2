import asyncio
from sqlalchemy import text
from app.database import engine

async def check_tables():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        tables = [row[0] for row in result]
        print("\nTables in database:")
        for table in tables:
            print(f"  ✓ {table}")
        print(f"\nTotal: {len(tables)} tables")
        return tables

asyncio.run(check_tables())
