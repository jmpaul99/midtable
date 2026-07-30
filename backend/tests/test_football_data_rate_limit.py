"""Tests for football-data.org rate-limit wait / retry behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest

from app.providers.base import RateLimitInfo
from app.providers.football_data import (
    FootballDataError,
    FootballDataProvider,
    rate_limit_wait_seconds,
)


def test_rate_limit_wait_prefers_retry_after_on_hit():
    rate = RateLimitInfo(
        requests_available_minute=0,
        retry_after_seconds=42,
        request_counter_reset=datetime.now(UTC) + timedelta(seconds=10),
    )
    assert rate_limit_wait_seconds(rate, hit_limit=True) == 42


def test_rate_limit_wait_uses_reset_when_retry_after_missing():
    rate = RateLimitInfo(
        requests_available_minute=0,
        request_counter_reset=datetime.now(UTC) + timedelta(seconds=17),
    )
    wait = rate_limit_wait_seconds(rate, hit_limit=True)
    assert wait is not None
    assert 17 <= wait <= 19


def test_rate_limit_wait_default_when_headers_missing():
    assert rate_limit_wait_seconds(RateLimitInfo(), hit_limit=True) == 60


def test_rate_limit_wait_low_budget_uses_reset():
    rate = RateLimitInfo(
        requests_available_minute=1,
        request_counter_reset=datetime.now(UTC) + timedelta(seconds=12),
    )
    wait = rate_limit_wait_seconds(rate, hit_limit=False)
    assert wait is not None
    assert 12 <= wait <= 14


def test_rate_limit_wait_none_when_budget_healthy():
    rate = RateLimitInfo(requests_available_minute=8)
    assert rate_limit_wait_seconds(rate, hit_limit=False) is None


def test_get_retries_after_429_using_retry_after(monkeypatch):
    client = MagicMock()
    limited = httpx.Response(
        429,
        headers={"Retry-After": "1", "X-Requests-Available-Minute": "0"},
        request=httpx.Request("GET", "https://api.football-data.org/v4/competitions/PL"),
    )
    ok = httpx.Response(
        200,
        json={"teams": []},
        headers={"X-Requests-Available-Minute": "9"},
        request=httpx.Request("GET", "https://api.football-data.org/v4/competitions/PL"),
    )
    client.get.side_effect = [limited, ok]
    provider = FootballDataProvider("token", client=client)

    sleeps: list[float] = []
    monkeypatch.setattr(
        "app.providers.football_data.time.sleep", lambda s: sleeps.append(s)
    )

    payload, rate = provider._get("/competitions/PL/teams", {"season": 2026})
    assert payload == {"teams": []}
    assert rate.requests_available_minute == 9
    assert sleeps == [1]
    assert client.get.call_count == 2


def test_resolve_competition_season_reraises_rate_limit():
    provider = FootballDataProvider("token", client=MagicMock())

    def boom(*_a, **_k):
        raise FootballDataError(
            "rate limit exceeded",
            RateLimitInfo(retry_after_seconds=5),
            rate_limited=True,
        )

    provider._get = boom  # type: ignore[method-assign]
    with pytest.raises(FootballDataError) as exc_info:
        provider.resolve_competition_season("PL", 2026)
    assert exc_info.value.rate_limited is True
