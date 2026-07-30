from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RateLimitInfo:
    requests_available_minute: int | None = None
    request_counter_reset: datetime | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class ProviderTeam:
    external_id: str
    name: str
    short_name: str | None = None
    tla: str | None = None
    crest_url: str | None = None


@dataclass(frozen=True)
class ProviderMatch:
    external_id: str
    home_external_id: str
    away_external_id: str
    kickoff_at: datetime
    status: str
    home_goals: int | None
    away_goals: int | None
    matchday: int | None
    stage: str | None
    duration: str = "REGULAR"


@dataclass(frozen=True)
class CompetitionSeasonInfo:
    code: str
    season_year: int
    start_date: datetime | None
    end_date: datetime | None
    available: bool
    message: str | None = None
    competition_type: str | None = None


@dataclass(frozen=True)
class ProviderStandingRow:
    external_team_id: str
    position: int
    played: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    team_name: str | None = None


class FootballProvider(Protocol):
    def list_teams(self, competition_code: str, season_year: int) -> tuple[list[ProviderTeam], RateLimitInfo]:
        ...

    def list_matches(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderMatch], RateLimitInfo]:
        ...

    def list_standings(
        self, competition_code: str, season_year: int
    ) -> tuple[list[ProviderStandingRow], RateLimitInfo]:
        ...

    def resolve_competition_season(
        self, competition_code: str, season_year: int
    ) -> tuple[CompetitionSeasonInfo, RateLimitInfo]:
        ...

    def resolve_competition_season_or_latest(
        self, competition_code: str, preferred_season_year: int
    ) -> tuple[CompetitionSeasonInfo, RateLimitInfo]:
        ...
