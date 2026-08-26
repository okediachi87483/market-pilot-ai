"""Health, liveness, and readiness — three distinct checks answering three
distinct questions. See docs/observability.md §4.

- GET /health        general status/version/environment info. Always 200
                      while the process can respond at all.
- GET /health/live    pure liveness. Always 200. Orchestration uses this
                      to decide "should this process be restarted?"
- GET /health/ready   dependency-checking readiness. 200 only if every
                      required dependency (Postgres, Redis) is reachable;
                      503 otherwise. Orchestration uses this to decide
                      "should this instance receive traffic right now?"
"""

from fastapi import APIRouter, Response, status

from app.core.config import APP_VERSION, get_settings
from app.db import redis as redis_db
from app.db import session as db_session
from app.schemas.health import (
    DependencyStatus,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="marketpilot-api",
        version=APP_VERSION,
        environment=settings.app_env,
    )


@router.get("/health/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    db_ok = await db_session.check_connection()
    redis_ok = await redis_db.check_connection()

    dependencies = {
        "postgres": DependencyStatus(status="ok" if db_ok else "down"),
        "redis": DependencyStatus(status="ok" if redis_ok else "down"),
    }
    all_ok = db_ok and redis_ok
    response.status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status="ok" if all_ok else "degraded", dependencies=dependencies)
