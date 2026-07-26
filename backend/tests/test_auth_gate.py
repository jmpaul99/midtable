"""Tests for AuthGateMiddleware allowlist."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from app.middleware import AuthGateMiddleware


def _request(method: str, path: str, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_health_allowed_without_auth():
    mw = AuthGateMiddleware(app=MagicMock())
    call_next = AsyncMock(return_value=MagicMock(status_code=200))
    with patch("app.middleware.get_settings") as gs:
        gs.return_value = MagicMock(
            auth_bypass_email="",
            is_production=False,
            is_development=True,
        )
        await mw.dispatch(_request("GET", "/health"), call_next)
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_leagues_requires_bearer():
    mw = AuthGateMiddleware(app=MagicMock())
    call_next = AsyncMock()
    with patch("app.middleware.get_settings") as gs:
        gs.return_value = MagicMock(
            auth_bypass_email="",
            is_production=True,
            is_development=False,
        )
        response = await mw.dispatch(_request("GET", "/leagues"), call_next)
    assert response.status_code == 401
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_status_requires_internal_header():
    mw = AuthGateMiddleware(app=MagicMock())
    call_next = AsyncMock()
    with patch("app.middleware.get_settings") as gs:
        gs.return_value = MagicMock(
            auth_bypass_email="",
            is_production=True,
            is_development=False,
        )
        response = await mw.dispatch(
            _request("POST", "/auth/email-status"),
            call_next,
        )
    assert response.status_code == 401
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_status_with_internal_header_passes_gate():
    mw = AuthGateMiddleware(app=MagicMock())
    call_next = AsyncMock(return_value=MagicMock(status_code=200))
    with patch("app.middleware.get_settings") as gs:
        gs.return_value = MagicMock(
            auth_bypass_email="",
            is_production=True,
            is_development=False,
        )
        await mw.dispatch(
            _request(
                "POST",
                "/auth/email-status",
                headers={"x-internal-secret": "x"},
            ),
            call_next,
        )
    call_next.assert_awaited_once()
