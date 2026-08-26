"""PostgreSQL connection management.

No domain schema is defined yet — see docs/database.md; the business
tables arrive with the packages that own them. This module only owns the
engine/session lifecycle and a connectivity check for the readiness probe.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    """Create the engine and session factory. Called once at app startup."""
    global _engine, _session_factory
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Close all pooled connections. Called once at app shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session. Not yet used
    by any route — wired in ahead of the first domain endpoint."""
    if _session_factory is None:
        raise RuntimeError("Database engine not initialized — init_engine() was not called")
    async with _session_factory() as session:
        yield session


async def check_connection() -> bool:
    """Used by GET /health/ready. Returns False on any failure rather than
    raising, so a dependency outage degrades the readiness response
    instead of crashing the health check itself."""
    if _engine is None:
        return False
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("readiness check: postgres unreachable: %s", exc)
        return False
