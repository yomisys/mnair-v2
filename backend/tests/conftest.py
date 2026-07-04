"""
Pytest configuration and fixtures for MNAIR backend tests
"""

import os

# Set required env vars before any app imports so Pydantic Settings doesn't fail.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-not-production")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")
os.environ.setdefault("DATABASE_PASSWORD", "mnair_password")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_password")

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
        # Route the FastAPI app's DB dependency to this session so route-level
        # tests (AsyncClient(app=app)) hit the in-memory test DB — never the
        # real dev/prod database configured in .env
        from app.main import app
        from app.database import get_db

        async def _override_get_db():
            yield session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db, None)

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Dispose engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db):
    """
    HTTP test client with the test database injected.
    Use this for route-level tests that need real HTTP semantics.
    """
    from httpx import AsyncClient as HttpxClient
    from app.main import app
    from app.database import get_db

    async def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with HttpxClient(app=app, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
