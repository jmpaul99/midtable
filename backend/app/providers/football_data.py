"""football-data.org v4 client with rate-limit header parsing."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.providers.base import (
    CompetitionSeasonInfo,
    ProviderMatch,
    ProviderStandingRow,
    ProviderTeam,
    RateLimitInfo,
)
from app.services.period_labels import normalize_competition_type

logger = logging.getLogger(__name__)

_KNOWN_TYPES = frozenset({"LEAGUE", "LEAGUE_CUP", "CUP", "PLAYOFFS"})
# Free-tier budget is ~10 req/min; admin syncs walk many competitions.
_MAX_RATE_LIMIT_RETRIES = 12


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


def rate_limit_wait_seconds(
    rate: RateLimitInfo,
    *,
    hit_limit: bool = False,
    low_budget_threshold: int = 2,
    default_hit_limit_wait: int = 60,
    default_low_budget_wait: int = 8,
) -> int | None:
    """Seconds to sleep before the next call, using response header info.

    Prefers ``Retry-After``, then ``X-RequestCounter-Reset``, then defaults.
    Returns ``None`` when no wait is needed.
    """

    def from_reset() -> int | None:
        if rate.request_counter_reset is None:
            return None
        secs = (rate.request_counter_reset - datetime.now(UTC)).total_seconds()
        return max(1, int(secs) + 1)

    if hit_limit:
        if rate.retry_after_seconds is not None:
            return max(1, int(rate.retry_after_seconds))
        reset_wait = from_reset()
        if reset_wait is not None:
            return reset_wait
        return default_hit_limit_wait

    if (
        rate.requests_available_minute is not None
        and rate.requests_available_minute <= low_budget_threshold
    ):
        if rate.retry_after_seconds is not None:
            return max(1, int(rate.retry_after_seconds))
        reset_wait = from_reset()
        if reset_wait is not None:
            return reset_wait
        return default_low_budget_wait
    return None


def respect_rate_limit(rate: RateLimitInfo, *, hit_limit: bool = False) -> None:
    """Block until football-data.org rate budget should allow another request."""
    wait = rate_limit_wait_seconds(rate, hit_limit=hit_limit)
    if wait is None:
        return
    logger.info(
        "football-data.org waiting for rate budget wait_s=%s hit_limit=%s "
        "available_minute=%s reset=%s retry_after=%s",
        wait,
        hit_limit,
        rate.requests_available_minute,
        rate.request_counter_reset,
        rate.retry_after_seconds,
    )
    time.sleep(wait)


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
        last_rate = RateLimitInfo()
        for attempt in range(1, _MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                logger.error(
                    "football-data.org request failed path=%s error=%s", path, exc
                )
                raise FootballDataError(
                    f"football-data.org request failed: {exc}"
                ) from exc
            rate = self.parse_rate_limit_headers(response.headers)
            last_rate = rate
            if response.status_code == 429:
                if attempt >= _MAX_RATE_LIMIT_RETRIES:
                    raise FootballDataError(
                        f"rate limit exceeded; retry after "
                        f"{rate.retry_after_seconds or 'unknown'}s",
                        rate,
                        rate_limited=True,
                    )
                wait = rate_limit_wait_seconds(rate, hit_limit=True) or 60
                logger.warning(
                    "football-data.org rate limited path=%s wait_s=%s attempt=%s/%s "
                    "retry_after=%s available_minute=%s reset=%s",
                    path,
                    wait,
                    attempt,
                    _MAX_RATE_LIMIT_RETRIES,
                    rate.retry_after_seconds,
                    rate.requests_available_minute,
                    rate.request_counter_reset,
                )
                time.sleep(wait)
                continue
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
                    "football-data.org low rate budget path=%s available_minute=%s "
                    "reset=%s",
                    path,
                    rate.requests_available_minute,
                    rate.request_counter_reset,
                )
            return response.json(), rate
        raise FootballDataError(
            "rate limit exceeded; retries exhausted",
            last_rate,
            rate_limited=True,
        )

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

    def list_standings(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderStandingRow], RateLimitInfo]:
        payload, rate = self._get(
            f"/competitions/{competition_code}/standings", {"season": season_year}
        )
        all_blocks = [
            block
            for block in (payload.get("standings") or [])
            if isinstance(block, dict)
        ]
        total_blocks = [
            block
            for block in all_blocks
            if str(block.get("type") or "").upper() == "TOTAL"
        ]
        overall = [
            block for block in total_blocks if block.get("group") in (None, "")
        ]
        if overall:
            # Domestic leagues: single overall TOTAL table.
            table_blocks = [overall[0]]
        elif total_blocks:
            # Multi-group cups: merge every TOTAL group table.
            table_blocks = total_blocks
        else:
            # No TOTAL blocks: merge remaining blocks so group-only payloads
            # still include every team rather than the first block alone.
            table_blocks = all_blocks

        rows: list[ProviderStandingRow] = []
        seen_team_ids: set[str] = set()
        for chosen in table_blocks:
            for item in chosen.get("table") or []:
                if not isinstance(item, dict):
                    continue
                team = item.get("team") or {}
                team_id = team.get("id")
                if team_id is None:
                    continue
                external_id = str(team_id)
                if external_id in seen_team_ids:
                    continue
                seen_team_ids.add(external_id)
                played = int(item.get("playedGames") or 0)
                goals_for = int(item.get("goalsFor") or 0)
                goals_against = int(item.get("goalsAgainst") or 0)
                gd = item.get("goalDifference")
                if gd is None:
                    gd = goals_for - goals_against
                rows.append(
                    ProviderStandingRow(
                        external_team_id=external_id,
                        position=int(item.get("position") or 0),
                        played=played,
                        points=int(item.get("points") or 0),
                        goals_for=goals_for,
                        goals_against=goals_against,
                        goal_difference=int(gd),
                        team_name=team.get("name"),
                    )
                )
        # Group-local positions are not a global order. When we merged multiple
        # blocks (multi-group cups / no overall TOTAL), re-rank by table metrics.
        if len(table_blocks) > 1:
            rows.sort(
                key=lambda r: (
                    -r.points,
                    -r.goal_difference,
                    -r.goals_for,
                    r.external_team_id,
                )
            )
            rows = [
                ProviderStandingRow(
                    external_team_id=row.external_team_id,
                    position=index,
                    played=row.played,
                    points=row.points,
                    goals_for=row.goals_for,
                    goals_against=row.goals_against,
                    goal_difference=row.goal_difference,
                    team_name=row.team_name,
                )
                for index, row in enumerate(rows, start=1)
            ]
        else:
            rows.sort(key=lambda r: (r.position, r.external_team_id))
        return rows, rate

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
            # Rate limits are transient; callers wait/retry. Other errors mean
            # the season is unavailable for this code/year.
            if exc.rate_limited:
                raise
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
            if exc.rate_limited:
                raise
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
