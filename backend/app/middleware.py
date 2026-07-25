"""HTTP middleware for request correlation and access logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import reset_request_id, set_request_id

logger = logging.getLogger("app.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = (
            incoming.strip()
            if incoming and incoming.strip()
            else str(uuid.uuid4())
        )
        token = set_request_id(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request failed method=%s path=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                duration_ms,
            )
            reset_request_id(token)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        path = request.url.path
        log = logger.debug if path == "/health" else logger.info
        log(
            "method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        reset_request_id(token)
        return response
