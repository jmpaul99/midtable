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
        # Fail fast on 429 — do not sleep here. Request handlers map rate limits to
        # ConflictError; background syncs wait/retry via respect_rate_limit.
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
        if response.status_code == 429:
            logger.warning(
                "football-data.org rate limited path=%s retry_after=%s "
                "available_minute=%s reset=%s",
                path,
                rate.retry_after_seconds,
                rate.requests_available_minute,
                rate.request_counter_reset,
            )
            raise FootballDataError(
                f"rate limit exceeded; retry after "
                f"{rate.retry_after_seconds or 'unknown'}s",
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
                "football-data.org low rate budget path=%s available_minute=%s "
                "reset=%s",
                path,
                rate.requests_available_minute,
                rate.request_counter_reset,
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

    @staticmethod
    def goals_from_score_block(block: Any) -> tuple[int | None, int | None]:
        """Read home/away goals from a score segment.

        football-data.org v4 normally uses ``home`` / ``away``. Older docs and
        some payloads still use ``homeTeam`` / ``awayTeam``. Missing both sides
        returns ``(None, None)``.
        """
        if not isinstance(block, dict):
            return None, None

        def _one(value: Any) -> int | None:
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        home = block.get("home")
        if home is None:
            home = block.get("homeTeam")
        away = block.get("away")
        if away is None:
            away = block.get("awayTeam")
        return _one(home), _one(away)

    @classmethod
    def goals_from_match_score(
        cls, score: Any, *, status: str
    ) -> tuple[int | None, int | None]:
        """Prefer fullTime; for finished matches fall back to regularTime/extraTime."""
        if not isinstance(score, dict):
            return None, None
        home_goals, away_goals = cls.goals_from_score_block(score.get("fullTime") or {})
        if home_goals is not None and away_goals is not None:
            return home_goals, away_goals
        # Finished rows with only legacy/regularTime/extraTime segments must still score.
        if str(status).upper() in {"FINISHED", "AWARDED"}:
            for key in ("regularTime", "extraTime"):
                alt_home, alt_away = cls.goals_from_score_block(score.get(key) or {})
                if alt_home is not None and alt_away is not None:
                    return alt_home, alt_away
            # One-sided legacy key fills (e.g. only homeTeam present on fullTime).
            if home_goals is not None or away_goals is not None:
                return home_goals, away_goals
        return home_goals, away_goals

    @classmethod
    def goals_from_goals_events(cls, goals: Any) -> tuple[int | None, int | None]:
        """Final score from the last goals[] event's running ``score`` block.

        The Match resource documents a ``goals`` array where each entry carries
        ``score: {home, away}`` (or legacy homeTeam/awayTeam). Competition list
        payloads sometimes leave ``score.fullTime`` null while still including
        this array — or omit both until ``GET /matches/{id}``.
        """
        if not isinstance(goals, list) or not goals:
            return None, None
        last = goals[-1]
        if not isinstance(last, dict):
            return None, None
        return cls.goals_from_score_block(last.get("score") or {})

    @classmethod
    def goals_from_match_payload(
        cls, item: dict[str, Any], *, status: str | None = None
    ) -> tuple[int | None, int | None]:
        """Resolve goals from score segments, then goals[] running score."""
        resolved_status = status if status is not None else str(item.get("status") or "")
        score = item.get("score") or {}
        home_goals, away_goals = cls.goals_from_match_score(
            score, status=resolved_status
        )
        if home_goals is not None and away_goals is not None:
            return home_goals, away_goals
        if str(resolved_status).upper() not in {"FINISHED", "AWARDED"}:
            return home_goals, away_goals
        event_home, event_away = cls.goals_from_goals_events(item.get("goals"))
        if event_home is not None and event_away is not None:
            return event_home, event_away
        return home_goals, away_goals

    def get_match(self, external_id: str) -> tuple[dict[str, Any], RateLimitInfo]:
        """Fetch a single Match resource (richer than competition list rows)."""
        payload, rate = self._get(f"/matches/{external_id}")
        if not isinstance(payload, dict):
            raise FootballDataError(
                f"football-data.org match {external_id} returned non-object payload",
                rate,
            )
        return payload, rate

    @staticmethod
    def _is_terminal_status(status: str) -> bool:
        return str(status).upper() in {"FINISHED", "AWARDED"}

    @classmethod
    def should_fetch_match_detail(
        cls,
        *,
        status: str,
        home_goals: int | None,
        away_goals: int | None,
        kickoff_at: datetime,
        now: datetime | None = None,
        overdue_after: timedelta = timedelta(hours=2),
    ) -> bool:
        """Whether competition-list data is too thin and needs GET /matches/{id}.

        - FINISHED/AWARDED list rows still missing goals (thin score payload)
        - Overdue non-terminal list rows (e.g. stuck TIMED) whose kickoff was
          at least ``overdue_after`` ago — detail often has the real FT status
        """
        goals_missing = home_goals is None or away_goals is None
        if cls._is_terminal_status(status) and goals_missing:
            return True
        if cls._is_terminal_status(status):
            return False
        clock = now or datetime.now(UTC)
        kickoff = kickoff_at if kickoff_at.tzinfo else kickoff_at.replace(tzinfo=UTC)
        overdue = clock - kickoff >= overdue_after
        # Non-terminal + overdue: always enrich (status not terminal ⇒ second
        # clause of "goals missing OR status not terminal" is true).
        return overdue and (goals_missing or not cls._is_terminal_status(status))

    def list_matches(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderMatch], RateLimitInfo]:
        payload, rate = self._get(
            f"/competitions/{competition_code}/matches", {"season": season_year}
        )
        matches: list[ProviderMatch] = []
        skipped_parse = 0
        finished_missing_goals = 0
        detail_enriched = 0
        now = datetime.now(UTC)
        for item in payload.get("matches", []):
            if not isinstance(item, dict):
                skipped_parse += 1
                continue
            score = item.get("score") or {}
            duration = str(
                (score.get("duration") if isinstance(score, dict) else None) or "REGULAR"
            )
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
            status = str(item.get("status") or "SCHEDULED")
            home_goals, away_goals = self.goals_from_match_payload(item, status=status)
            # Competition /matches list is thinner than GET /matches/{id}. Enrich
            # when finished rows lack goals, or overdue rows are still non-terminal
            # (TIMED/SCHEDULED/IN_PLAY) so Saturday fixtures can become FINISHED.
            if item.get("id") is not None and self.should_fetch_match_detail(
                status=status,
                home_goals=home_goals,
                away_goals=away_goals,
                kickoff_at=kickoff,
                now=now,
            ):
                try:
                    respect_rate_limit(rate)
                    detail, rate = self.get_match(str(item["id"]))
                    detail_status = str(detail.get("status") or status)
                    detail_home, detail_away = self.goals_from_match_payload(
                        detail, status=detail_status
                    )
                    # Only apply detail when it actually finishes the match (or
                    # fills goals on an already-terminal list row).
                    if self._is_terminal_status(detail_status):
                        status = detail_status
                        if detail_home is not None and detail_away is not None:
                            home_goals, away_goals = detail_home, detail_away
                        detail_enriched += 1
                        detail_score = detail.get("score") or {}
                        if isinstance(detail_score, dict) and detail_score.get(
                            "duration"
                        ):
                            duration = str(detail_score.get("duration") or duration)
                    elif (
                        self._is_terminal_status(status)
                        and detail_home is not None
                        and detail_away is not None
                    ):
                        home_goals, away_goals = detail_home, detail_away
                        detail_enriched += 1
                except FootballDataError as exc:
                    if exc.rate_limit.requests_available_minute is not None or (
                        exc.rate_limit.retry_after_seconds is not None
                    ):
                        rate = exc.rate_limit
                    logger.warning(
                        "football-data.org detail goals fetch failed competition=%s "
                        "season=%s external_id=%s error=%s",
                        competition_code,
                        season_year,
                        item.get("id"),
                        exc,
                    )
            if (
                status.upper() in {"FINISHED", "AWARDED"}
                and (home_goals is None or away_goals is None)
            ):
                finished_missing_goals += 1
                logger.warning(
                    "football-data.org finished match missing goals competition=%s "
                    "season=%s external_id=%s status=%s score_keys=%s fullTime=%s "
                    "goals_events=%s",
                    competition_code,
                    season_year,
                    item.get("id"),
                    status,
                    sorted(score.keys()) if isinstance(score, dict) else None,
                    score.get("fullTime") if isinstance(score, dict) else None,
                    len(item.get("goals") or [])
                    if isinstance(item.get("goals"), list)
                    else 0,
                )
            matches.append(
                ProviderMatch(
                    external_id=str(item["id"]),
                    home_external_id=str(home["id"]),
                    away_external_id=str(away["id"]),
                    kickoff_at=kickoff,
                    status=status,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    matchday=item.get("matchday"),
                    stage=item.get("stage"),
                    duration=duration,
                )
            )
        if skipped_parse or finished_missing_goals or detail_enriched:
            logger.warning(
                "football-data.org parse skips competition=%s season=%s skipped=%s "
                "finished_missing_goals=%s detail_enriched=%s kept=%s",
                competition_code,
                season_year,
                skipped_parse,
                finished_missing_goals,
                detail_enriched,
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
                raw_position = item.get("position")
                try:
                    position = int(raw_position) if raw_position is not None else 0
                except (TypeError, ValueError):
                    position = 0
                rows.append(
                    ProviderStandingRow(
                        external_team_id=external_id,
                        position=position,
                        played=played,
                        points=int(item.get("points") or 0),
                        goals_for=goals_for,
                        goals_against=goals_against,
                        goal_difference=int(gd),
                        team_name=team.get("name"),
                    )
                )
        # Re-rank when we merged multiple blocks (group-local positions) or when
        # any row lacks a valid position (>= 1), so missing/zero ranks cannot
        # sort ahead of real table places for draft snapshots / autopick.
        needs_rerank = len(table_blocks) > 1 or any(r.position < 1 for r in rows)
        if needs_rerank:
            rows = self._rerank_standing_rows(rows)
        else:
            rows.sort(key=lambda r: (r.position, r.external_team_id))
        return rows, rate

    @staticmethod
    def _rerank_standing_rows(
        rows: list[ProviderStandingRow],
    ) -> list[ProviderStandingRow]:
        ordered = sorted(
            rows,
            key=lambda r: (
                -r.points,
                -r.goal_difference,
                -r.goals_for,
                r.external_team_id,
            ),
        )
        return [
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
            for index, row in enumerate(ordered, start=1)
        ]

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
