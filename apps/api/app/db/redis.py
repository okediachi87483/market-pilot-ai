"""Redis connection management — cache and pub/sub only, never authoritative.

See docs/data-flow.md §2. No caching strategy or queues are implemented
yet (Phase 2 is foundation only); this module owns connection lifecycle
and a connectivity check for the readiness probe.
"""

from typing import cast

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Redis | None = None


def init_client() -> Redis:
    """Create the Redis client. Called once at app startup."""
    global _client
    settings = get_settings()
    client = cast(Redis, Redis.from_url(settings.redis_url, decode_responses=True))
    _client = client
    return client


async def dispose_client() -> None:
    """Close the connection pool. Called once at app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def check_connection() -> bool:
    """Used by GET /health/ready. Returns False on any failure rather than
    raising."""
    if _client is None:
        return False
    try:
        return bool(await _client.ping())
    except Exception as exc:
        logger.warning("readiness check: redis unreachable: %s", exc)
        return False
