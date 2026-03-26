"""
Simple Database Initialization Script (Windows Compatible)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, Base
from app.models import User, Lesson, LessonProgress, QuizAttempt, Certificate, Conversation, Employer, Analytics

async def create_tables():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] All tables created successfully!")

async def main():
    try:
        await create_tables()
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
