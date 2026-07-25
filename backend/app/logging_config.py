"""Central logging configuration for the API."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from app.config import Settings

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_var.get()


def log_id(obj: object, *attrs: str) -> str:
    """Best-effort id for log lines (tolerates test doubles without public_id)."""
    names = attrs or ("public_id", "id")
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return str(value)
    return "?"


def set_request_id(request_id: str | None) -> Token[str | None]:
    return _request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Configure root logging. Safe to call multiple times (e.g. uvicorn --reload)."""
    level_name = (settings.log_level or "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())

    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(request_id)s %(message)s"
            )
        )

    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ug = logging.getLogger(name)
        ug.handlers.clear()
        ug.propagate = True
        ug.setLevel(level)

    logging.getLogger("app").setLevel(level)

    # Keep client libraries quiet unless explicitly debugging.
    for name in ("httpx", "httpcore", "hpack"):
        logging.getLogger(name).setLevel(logging.WARNING)
