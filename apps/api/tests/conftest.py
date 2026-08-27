import os
import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Point at the Postgres/Redis exposed by `docker compose up -d postgres
# redis` (see docker-compose.yml — host port 5433 for postgres, per the
# Phase 2 port-conflict fix) unless the environment already overrides
# them. Must run before any app module reads Settings, since get_settings()
# is cached for the process lifetime.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "marketpilot")
os.environ.setdefault("POSTGRES_USER", "marketpilot")
os.environ.setdefault("POSTGRES_PASSWORD", "marketpilot")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def unique_symbol(prefix: str = "TEST") -> str:
    """A symbol guaranteed not to collide with the seeded fixture assets
    or with other test runs, for tests that need their own Asset row."""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip(
            "live Postgres not reachable — start it with `docker compose up -d postgres` "
            "(see README.md)"
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
