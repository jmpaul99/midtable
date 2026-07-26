"""HTTP middleware for request correlation, access logging, and default-deny auth."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.logging_config import reset_request_id, set_request_id

logger = logging.getLogger("app.access")

_PUBLIC_GET_PATHS = frozenset({"/health", "/join-links/preview"})
_DEV_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


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


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Default-deny: only allowlisted public/secret-gated paths skip Bearer JWT."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        settings = get_settings()

        # Dev auth bypass authenticates without a Bearer token (see get_current_user).
        if settings.auth_bypass_email.strip() and not settings.is_production:
            return await call_next(request)

        if request.method == "GET" and path in _PUBLIC_GET_PATHS:
            return await call_next(request)

        if (
            settings.is_development
            and request.method == "GET"
            and (path in _DEV_DOCS_PATHS or path.startswith("/docs/"))
        ):
            return await call_next(request)

        if request.method == "POST" and path.startswith("/internal/"):
            if request.headers.get("x-cron-secret"):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer token required"},
            )

        if request.method == "POST" and path == "/auth/email-status":
            if request.headers.get("x-internal-secret"):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer token required"},
            )

        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer ") and auth[7:].strip():
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Bearer token required"},
        )
