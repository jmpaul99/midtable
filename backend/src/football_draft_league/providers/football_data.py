import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from football_draft_league.providers.base import ProviderResponse, RateLimit


class FootballDataError(RuntimeError):
    def __init__(
        self,
        message: str,
        rate_limit: RateLimit | None = None,
        *,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.rate_limit = rate_limit or RateLimit()
        self.rate_limited = rate_limited


class FootballDataProvider:
    """Async football-data.org v4 adapter with bounded batched requests."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = "https://api.football-data.org/v4",
        requests_per_minute: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_token:
            raise ValueError("football-data.org API token is required")
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Auth-Token": api_token},
            timeout=httpx.Timeout(15.0),
        )
        self._owns_client = client is None
        self._concurrency = asyncio.Semaphore(max(1, min(requests_per_minute, 4)))
        self._rate_lock = asyncio.Lock()
        self._minimum_interval = 60 / requests_per_minute
        self._next_request_at = 0.0

    @staticmethod
    def _rate_limit(headers: httpx.Headers) -> RateLimit:
        def integer(name: str) -> int | None:
            raw = headers.get(name)
            return int(raw) if raw and raw.isdigit() else None

        reset_at = None
        reset = headers.get("x-requestcounter-reset")
        if reset:
            try:
                reset_at = datetime.now(UTC) + timedelta(seconds=int(reset))
            except ValueError:
                try:
                    reset_at = parsedate_to_datetime(reset).astimezone(UTC)
                except (TypeError, ValueError):
                    pass
        return RateLimit(
            limit=integer("x-requests-available-minute"),
            remaining=(
                integer("x-requests-remaining")
                if headers.get("x-requests-remaining") is not None
                else integer("x-requests-available-minute")
            ),
            reset_at=reset_at,
            retry_after_seconds=integer("retry-after"),
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, RateLimit]:
        async with self._rate_lock:
            loop = asyncio.get_running_loop()
            delay = self._next_request_at - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = loop.time() + self._minimum_interval
        async with self._concurrency:
            response = await self._client.get(path, params=params)
        if response.status_code == 429:
            rate = self._rate_limit(response.headers)
            raise FootballDataError(
                f"football-data.org rate limit exceeded; retry after "
                f"{rate.retry_after_seconds or 'unknown'} seconds",
                rate,
                rate_limited=True,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FootballDataError(
                f"football-data.org returned {response.status_code}"
            ) from exc
        return response.json(), self._rate_limit(response.headers)

    async def _batch(
        self,
        codes: Sequence[str],
        endpoint: str,
        item_key: str | None,
        params: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        unique_codes = tuple(dict.fromkeys(codes))
        if not unique_codes:
            return ProviderResponse((), RateLimit(), datetime.now(UTC))
        responses = await asyncio.gather(
            *(self._get(endpoint.format(code=code), params) for code in unique_codes)
        )
        items: list[dict[str, Any]] = []
        limits: list[RateLimit] = []
        for payload, rate_limit in responses:
            limits.append(rate_limit)
            values = payload.get(item_key, []) if item_key else [payload]
            items.extend(values)
        remaining = [limit.remaining for limit in limits if limit.remaining is not None]
        return ProviderResponse(
            tuple(items),
            RateLimit(
                remaining=min(remaining) if remaining else None,
                reset_at=max(
                    (limit.reset_at for limit in limits if limit.reset_at), default=None
                ),
                retry_after_seconds=max(
                    (limit.retry_after_seconds or 0 for limit in limits), default=0
                )
                or None,
            ),
            datetime.now(UTC),
        )

    async def competitions(self, codes: Sequence[str]) -> ProviderResponse:
        return await self._batch(codes, "/competitions/{code}", None)

    async def teams(self, competition_codes: Sequence[str], season: int) -> ProviderResponse:
        return await self._batch(
            competition_codes, "/competitions/{code}/teams", "teams", {"season": season}
        )

    async def matches(
        self,
        competition_codes: Sequence[str],
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: Sequence[str] = (),
    ) -> ProviderResponse:
        params: dict[str, Any] = {}
        if date_from:
            params["dateFrom"] = date_from.date().isoformat()
        if date_to:
            params["dateTo"] = date_to.date().isoformat()
        if statuses:
            params["status"] = ",".join(statuses)
        return await self._batch(
            competition_codes, "/competitions/{code}/matches", "matches", params
        )

    async def standings(
        self, competition_codes: Sequence[str], season: int
    ) -> ProviderResponse:
        return await self._batch(
            competition_codes,
            "/competitions/{code}/standings",
            "standings",
            {"season": season},
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "FootballDataProvider":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
