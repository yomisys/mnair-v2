"""
Pytest configuration and fixtures for MNAIR backend tests
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
# Import all models to register them with Base.metadata
import app.models  # noqa: F401


# Test database URL (use in-memory SQLite for fast tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure pytest-asyncio default loop scope"""
    config.option.asyncio_default_fixture_loop_scope = "function"


@pytest_asyncio.fixture
async def test_db():
    """
    Create a fresh database for each test function
    Uses in-memory SQLite for speed
    """
    # Create async engine with StaticPool to keep same connection
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session directly bound to engine
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Dispose engine
    await engine.dispose()
