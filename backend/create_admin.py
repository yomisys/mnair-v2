"""
Create Admin User Script (Windows Compatible)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import AsyncSessionLocal
from app.models.user import User
from app.utils.auth import get_password_hash

async def create_admin():
    """Create an admin user account"""
    print("Creating admin user...")

    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.phone_number == "+2348000000000")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("[INFO] Admin user already exists")
            return

        # Create admin user
        admin = User(
            phone_number="+2348000000000",
            name="MNAIR Administrator",
            role="admin",
            language="en",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            consent_given=True
        )

        db.add(admin)
        await db.commit()

        print("[OK] Admin user created successfully!")
        print("")
        print("Login Credentials:")
        print("  Phone: +2348000000000")
        print("  Password: admin123")
        print("")
        print("[WARNING] Change this password immediately in production!")

async def main():
    try:
        await create_admin()
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
