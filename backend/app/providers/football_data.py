"""football-data.org v4 client with rate-limit header parsing."""

from __future__ import annotations

import logging
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
from app.services.period_labels import normalize_competition_type

logger = logging.getLogger(__name__)

_KNOWN_TYPES = frozenset({"LEAGUE", "LEAGUE_CUP", "CUP", "PLAYOFFS"})


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
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            logger.error("football-data.org request failed path=%s error=%s", path, exc)
            raise FootballDataError(f"football-data.org request failed: {exc}") from exc
        rate = self.parse_rate_limit_headers(response.headers)
        if response.status_code == 429:
            logger.warning(
                "football-data.org rate limited path=%s retry_after=%s available_minute=%s",
                path,
                rate.retry_after_seconds,
                rate.requests_available_minute,
            )
            raise FootballDataError(
                f"rate limit exceeded; retry after {rate.retry_after_seconds or 'unknown'}s",
                rate,
                rate_limited=True,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "football-data.org HTTP error path=%s status=%s",
                path,
                response.status_code,
            )
            raise FootballDataError(
                f"football-data.org returned {response.status_code}", rate
            ) from exc
        if (
            rate.requests_available_minute is not None
            and rate.requests_available_minute <= 2
        ):
            logger.warning(
                "football-data.org low rate budget path=%s available_minute=%s",
                path,
                rate.requests_available_minute,
            )
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
        skipped_parse = 0
        for item in payload.get("matches", []):
            score = item.get("score") or {}
            full = score.get("fullTime") or {}
            duration = str(score.get("duration") or "REGULAR")
            utc_date = item.get("utcDate")
            if not utc_date:
                skipped_parse += 1
                continue
            kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).astimezone(UTC)
            home = item.get("homeTeam") or {}
            away = item.get("awayTeam") or {}
            if not home.get("id") or not away.get("id"):
                skipped_parse += 1
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
                    duration=duration,
                )
            )
        if skipped_parse:
            logger.warning(
                "football-data.org parse skips competition=%s season=%s skipped=%s kept=%s",
                competition_code,
                season_year,
                skipped_parse,
                len(matches),
            )
        return matches, rate

    @staticmethod
    def _parse_provider_date(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value).replace(tzinfo=UTC)

    @staticmethod
    def _competition_type_from_payload(payload: dict[str, Any]) -> str | None:
        raw = payload.get("type")
        normalized = normalize_competition_type(str(raw) if raw is not None else None)
        if normalized in _KNOWN_TYPES:
            return normalized
        return None

    @staticmethod
    def _season_start_year(season: dict[str, Any]) -> int | None:
        start = str(season.get("startDate") or "")
        if len(start) >= 4 and start[:4].isdigit():
            return int(start[:4])
        return None

    def _pick_season(
        self,
        payload: dict[str, Any],
        *,
        preferred_season_year: int | None = None,
        allow_latest_fallback: bool = False,
    ) -> tuple[dict[str, Any] | None, int | None]:
        raw_seasons = [s for s in (payload.get("seasons") or []) if isinstance(s, dict)]
        current = payload.get("currentSeason")
        candidates: list[dict[str, Any]] = []
        seen: set[object] = set()
        for season in (
            [current, *raw_seasons] if isinstance(current, dict) else raw_seasons
        ):
            key = season.get("id") or season.get("startDate")
            if key is not None and key in seen:
                continue
            if key is not None:
                seen.add(key)
            candidates.append(season)

        if preferred_season_year is not None:
            for season in candidates:
                if self._season_start_year(season) == preferred_season_year:
                    return season, preferred_season_year

        if not allow_latest_fallback:
            return None, preferred_season_year

        dated = [
            (self._season_start_year(s), s)
            for s in candidates
            if self._season_start_year(s) is not None
        ]
        if not dated:
            return None, preferred_season_year
        dated.sort(key=lambda item: item[0] or 0, reverse=True)
        year, season = dated[0]
        return season, year

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
        match, resolved_year = self._pick_season(
            payload, preferred_season_year=season_year, allow_latest_fallback=False
        )
        if match is None or resolved_year is None:
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

        return (
            CompetitionSeasonInfo(
                code=competition_code,
                season_year=resolved_year,
                start_date=self._parse_provider_date(match.get("startDate")),
                end_date=self._parse_provider_date(match.get("endDate")),
                available=True,
                competition_type=self._competition_type_from_payload(payload),
            ),
            rate,
        )

    def resolve_competition_season_or_latest(
        self, competition_code: str, preferred_season_year: int
    ) -> tuple[CompetitionSeasonInfo, RateLimitInfo]:
        """Prefer ``preferred_season_year``; otherwise use the newest published season.

        Useful for tournaments that are not annual (World Cup, Euros).
        """
        try:
            payload, rate = self._get(f"/competitions/{competition_code}")
        except FootballDataError as exc:
            return (
                CompetitionSeasonInfo(
                    code=competition_code,
                    season_year=preferred_season_year,
                    start_date=None,
                    end_date=None,
                    available=False,
                    message=str(exc),
                ),
                exc.rate_limit,
            )
        match, resolved_year = self._pick_season(
            payload,
            preferred_season_year=preferred_season_year,
            allow_latest_fallback=True,
        )
        if match is None or resolved_year is None:
            return (
                CompetitionSeasonInfo(
                    code=competition_code,
                    season_year=preferred_season_year,
                    start_date=None,
                    end_date=None,
                    available=False,
                    message="no seasons published by provider",
                ),
                rate,
            )
        message = None
        if resolved_year != preferred_season_year:
            message = (
                f"using latest available season {resolved_year} "
                f"(requested {preferred_season_year})"
            )
        return (
            CompetitionSeasonInfo(
                code=competition_code,
                season_year=resolved_year,
                start_date=self._parse_provider_date(match.get("startDate")),
                end_date=self._parse_provider_date(match.get("endDate")),
                available=True,
                message=message,
                competition_type=self._competition_type_from_payload(payload),
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
