"""Tests for logging configuration, request IDs, and exception handlers."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from app.main import app, unhandled_exception_handler
from app.middleware import RequestLoggingMiddleware
from app.services.errors import DomainError


def test_configure_logging_respects_log_level():
    settings = Settings(app_env="development", log_level="WARNING")
    configure_logging(settings)
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("app").level == logging.WARNING


def test_configure_logging_json_in_production():
    settings = Settings(app_env="production", log_level="INFO", cron_secret="test-secret")
    # Avoid validate_runtime; only need is_production for formatter choice
    configure_logging(settings)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_json_formatter_includes_request_id():
    token = set_request_id("req-abc")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        RequestIdFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["message"] == "hello"
        assert payload["request_id"] == "req-abc"
        assert payload["level"] == "INFO"
    finally:
        reset_request_id(token)


def test_health_sets_request_id_header():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    custom = client.get("/health", headers={"X-Request-ID": "client-id-1"})
    assert custom.headers.get("x-request-id") == "client-id-1"


def test_health_access_log_is_debug(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger="app.access"):
        client = TestClient(app)
        client.get("/health")
    access_records = [r for r in caplog.records if r.name == "app.access"]
    assert access_records
    assert all(r.levelno == logging.DEBUG for r in access_records)


def test_root_access_log_is_info(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger="app.access"):
        client = TestClient(app)
        client.get("/")
    access_records = [r for r in caplog.records if r.name == "app.access" and "path=/" in r.getMessage()]
    assert access_records
    assert any(r.levelno == logging.INFO for r in access_records)


def test_domain_error_is_logged(caplog: pytest.LogCaptureFixture):
    test_app = FastAPI()
    test_app.add_middleware(RequestLoggingMiddleware)

    @test_app.get("/boom-domain")
    def boom_domain():
        raise DomainError("nope", status_code=400)

    @test_app.exception_handler(DomainError)
    async def domain_handler(request: Request, exc: DomainError) -> JSONResponse:
        logging.getLogger("app.main").warning(
            "DomainError status=%s path=%s detail=%s",
            exc.status_code,
            request.url.path,
            exc.message,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    with caplog.at_level(logging.WARNING):
        client = TestClient(test_app)
        response = client.get("/boom-domain")
    assert response.status_code == 400
    assert any("DomainError" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_unhandled_exception_handler_logs_and_hides_detail(
    caplog: pytest.LogCaptureFixture,
):
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/explode",
            "raw_path": b"/explode",
            "query_string": b"",
            "headers": [],
            "client": ("test", 123),
            "server": ("test", 80),
        }
    )
    with caplog.at_level(logging.ERROR):
        response = await unhandled_exception_handler(request, RuntimeError("secret"))
    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'
    assert any("Unhandled error" in r.getMessage() for r in caplog.records)


def test_request_id_context_roundtrip():
    assert get_request_id() is None
    token = set_request_id("ctx-1")
    try:
        assert get_request_id() == "ctx-1"
    finally:
        reset_request_id(token)
    assert get_request_id() is None
