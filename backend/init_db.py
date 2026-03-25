"""
Database Initialization Script
Creates all tables and runs migrations
"""

import asyncio
import sys
from pathlib import Path

# Add backend to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, Base, init_db
from app.models import (
    User,
    Lesson,
    LessonProgress,
    QuizAttempt,
    Certificate,
    Conversation,
    Employer,
    Analytics,
)


async def create_tables():
    """Create all database tables"""
    print("Creating database tables...")

    async with engine.begin() as conn:
        # Drop all tables (careful in production!)
        # await conn.run_sync(Base.metadata.drop_all)
        # print("✅ Dropped existing tables")

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Created all tables")

    print("\n📊 Tables created:")
    print("  - users")
    print("  - lessons")
    print("  - lesson_progress")
    print("  - quiz_attempts")
    print("  - certificates")
    print("  - conversations")
    print("  - employers")
    print("  - analytics")


async def verify_tables():
    """Verify tables exist"""
    from sqlalchemy import text

    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """)
        )

        tables = [row[0] for row in result]

        print("\n✅ Verified tables in database:")
        for table in tables:
            print(f"  - {table}")

        expected_tables = [
            "users",
            "lessons",
            "lesson_progress",
            "quiz_attempts",
            "certificates",
            "conversations",
            "employers",
            "analytics",
        ]

        missing = set(expected_tables) - set(tables)
        if missing:
            print(f"\n⚠️  Missing tables: {missing}")
            return False

        print(f"\n✅ All {len(expected_tables)} tables exist!")
        return True


async def main():
    """Main initialization function"""
    print("=" * 60)
    print("MNAIR Platform - Database Initialization")
    print("=" * 60)

    try:
        # Create tables
        await create_tables()

        # Verify tables
        await verify_tables()

        print("\n" + "=" * 60)
        print("✅ Database initialization complete!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
