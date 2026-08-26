"""Structured JSON logging, shared by every module.

One configuration for the whole process — see docs/observability.md §1.
Every log line is a single JSON object with at minimum: timestamp, level,
service, message, and request_id when available. Nothing secret-shaped
(passwords, API keys, tokens) is ever logged; callers must not pass such
values as log fields.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

SERVICE_NAME = "marketpilot-api"

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "message": record.getMessage(),
            "logger": record.name,
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Uvicorn's own loggers should use the same JSON format instead of
    # their default colorized text output.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [handler]
        uv_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
