import asyncio
from sqlalchemy import text
from app.database import engine

async def verify():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))
        tables = [row[0] for row in result]
       
        print("\nDatabase Tables:")
        for t in tables:
            print(f"  - {t}")
        print(f"\n[OK] {len(tables)} tables exist\n")
        
        expected = ['users', 'lessons', 'lesson_progress', 'quiz_attempts', 'certificates', 'conversations', 'employers', 'analytics']
        missing = set(expected) - set(tables)
        if missing:
            print(f"[WARN] Missing: {missing}")
        else:
            print("[SUCCESS] All expected tables exist!")
    await engine.dispose()

asyncio.run(verify())
