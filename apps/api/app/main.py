"""FastAPI application entrypoint — composition root.

Per docs/architecture.md §3: this module wires routers to package
services and owns startup/shutdown. No business logic lives here.
"""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import APP_VERSION, get_settings
from app.core.logging import configure_logging, get_logger, set_request_id
from app.db import redis as redis_db
from app.db import session as db_session

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting marketpilot-api version=%s env=%s", APP_VERSION, settings.app_env)

    db_session.init_engine()
    redis_db.init_client()

    yield

    logger.info("shutting down marketpilot-api")
    await db_session.dispose_engine()
    await redis_db.dispose_client()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="MarketPilot AI API",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app


app = create_app()
