"""football-data.org v4 client with rate-limit header parsing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.providers.base import (
    CompetitionSeasonInfo,
    ProviderMatch,
    ProviderTeam,
    RateLimitInfo,
)


class FootballDataError(RuntimeError):
    def __init__(
        self,
        message: str,
        rate_limit: RateLimitInfo | None = None,
        *,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.rate_limit = rate_limit or RateLimitInfo()
        self.rate_limited = rate_limited


class FootballDataProvider:
    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = "https://api.football-data.org/v4",
        client: httpx.Client | None = None,
    ) -> None:
        if not api_token:
            raise ValueError("football-data.org API token is required")
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Auth-Token": api_token},
            timeout=httpx.Timeout(20.0),
        )
        self._owns_client = client is None

    @staticmethod
    def parse_rate_limit_headers(headers: httpx.Headers | dict[str, str]) -> RateLimitInfo:
        def get(name: str) -> str | None:
            if hasattr(headers, "get"):
                return headers.get(name) or headers.get(name.title())
            return None

        def integer(name: str) -> int | None:
            raw = get(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        reset_at = None
        reset = get("X-RequestCounter-Reset") or get("x-requestcounter-reset")
        if reset:
            try:
                reset_at = datetime.now(UTC) + timedelta(seconds=int(reset))
            except ValueError:
                try:
                    reset_at = parsedate_to_datetime(reset).astimezone(UTC)
                except (TypeError, ValueError):
                    reset_at = None

        return RateLimitInfo(
            requests_available_minute=integer("X-Requests-Available-Minute")
            or integer("x-requests-available-minute"),
            request_counter_reset=reset_at,
            retry_after_seconds=integer("Retry-After") or integer("retry-after"),
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, RateLimitInfo]:
        response = self._client.get(path, params=params)
        rate = self.parse_rate_limit_headers(response.headers)
        if response.status_code == 429:
            raise FootballDataError(
                f"rate limit exceeded; retry after {rate.retry_after_seconds or 'unknown'}s",
                rate,
                rate_limited=True,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FootballDataError(
                f"football-data.org returned {response.status_code}", rate
            ) from exc
        return response.json(), rate

    def list_teams(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderTeam], RateLimitInfo]:
        payload, rate = self._get(
            f"/competitions/{competition_code}/teams", {"season": season_year}
        )
        teams = [
            ProviderTeam(
                external_id=str(item["id"]),
                name=item["name"],
                short_name=item.get("shortName"),
                tla=item.get("tla"),
                crest_url=item.get("crest"),
            )
            for item in payload.get("teams", [])
        ]
        return teams, rate

    def list_matches(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderMatch], RateLimitInfo]:
        payload, rate = self._get(
            f"/competitions/{competition_code}/matches", {"season": season_year}
        )
        matches: list[ProviderMatch] = []
        for item in payload.get("matches", []):
            score = item.get("score") or {}
            full = score.get("fullTime") or {}
            utc_date = item.get("utcDate")
            if not utc_date:
                continue
            kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).astimezone(UTC)
            home = item.get("homeTeam") or {}
            away = item.get("awayTeam") or {}
            if not home.get("id") or not away.get("id"):
                continue
            matches.append(
                ProviderMatch(
                    external_id=str(item["id"]),
                    home_external_id=str(home["id"]),
                    away_external_id=str(away["id"]),
                    kickoff_at=kickoff,
                    status=str(item.get("status") or "SCHEDULED"),
                    home_goals=full.get("home"),
                    away_goals=full.get("away"),
                    matchday=item.get("matchday"),
                    stage=item.get("stage"),
                )
            )
        return matches, rate

    def resolve_competition_season(
        self, competition_code: str, season_year: int
    ) -> tuple[CompetitionSeasonInfo, RateLimitInfo]:
        try:
            payload, rate = self._get(f"/competitions/{competition_code}")
        except FootballDataError as exc:
            return (
                CompetitionSeasonInfo(
                    code=competition_code,
                    season_year=season_year,
                    start_date=None,
                    end_date=None,
                    available=False,
                    message=str(exc),
                ),
                exc.rate_limit,
            )
        seasons = payload.get("seasons") or []
        match = next((s for s in seasons if s.get("startDate", "").startswith(str(season_year))), None)
        if match is None:
            # football-data often uses start year; also try currentSeason
            current = payload.get("currentSeason") or {}
            if str(current.get("startDate", "")).startswith(str(season_year)):
                match = current
        if match is None:
            return (
                CompetitionSeasonInfo(
                    code=competition_code,
                    season_year=season_year,
                    start_date=None,
                    end_date=None,
                    available=False,
                    message="season not published by provider",
                ),
                rate,
            )

        def parse_date(value: str | None) -> datetime | None:
            if not value:
                return None
            return datetime.fromisoformat(value).replace(tzinfo=UTC)

        return (
            CompetitionSeasonInfo(
                code=competition_code,
                season_year=season_year,
                start_date=parse_date(match.get("startDate")),
                end_date=parse_date(match.get("endDate")),
                available=True,
            ),
            rate,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FootballDataProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
