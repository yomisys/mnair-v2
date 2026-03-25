import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, Base
from app.models import (
    User, Lesson, LessonProgress, QuizAttempt,
    Certificate, Conversation, Employer, Analytics,
)

async def main():
    print("=" * 60)
    print("MNAIR - Database Initialization")
    print("=" * 60)
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] Created all tables")
        
        from sqlalchemy import text
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            tables = [row[0] for row in result]
            
            print("\nTables in database:")
            for table in tables:
                print(f"  - {table}")
            
            print(f"\nTotal: {len(tables)} tables created")
            print("=" * 60)
            print("[SUCCESS] Database initialization complete!")
            print("=" * 60)
            
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
