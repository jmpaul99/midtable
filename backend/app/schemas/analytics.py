"""Analytics API response models."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StandingsPhaseMeta(BaseModel):
    key: str
    name: str
    matchweek_range: list[int] | None = None
    stage_in: list[str] | None = None
    include_bonus_types: list[str] = Field(default_factory=list)
    matching_matches: int = 0
    finished_matches: int = 0
    remaining_matches: int = 0
    is_final: bool = False


class StandingEntry(BaseModel):
    rank: int
    member_id: UUID
    display_name: str
    team_name: str | None = None
    owner_name: str | None = None
    total_points: float
    upset_points: float
    win_count: int
    payout: float | int = 0
    metric_values: list[dict[str, Any]] = Field(default_factory=list)
    rung_values: list[Any] = Field(default_factory=list)


class StandingsResponse(BaseModel):
    phase: StandingsPhaseMeta
    entries: list[StandingEntry]


class PointsPerGameRow(BaseModel):
    team_id: UUID | None = None
    team_name: str | None = None
    member_id: UUID | None = None
    display_name: str | None = None
    points: float
    games_played: int
    points_per_game: float


class MatchweekStatRow(BaseModel):
    member_id: UUID
    display_name: str
    scheduled_matchweek: int
    points: float


class UpsetStatRow(BaseModel):
    member_id: UUID
    display_name: str
    count: int
    points: float
    upset_count: int | None = None
    upset_points: float | None = None
    by_type: dict[str, float] | None = None


class FormStatRow(BaseModel):
    team_id: UUID
    team_name: str
    member_id: UUID
    display_name: str
    form: list[str] = Field(default_factory=list)
    current_streak: dict[str, Any] | None = None
    wins: int = 0
    draws: int = 0
    losses: int = 0
    games_played: int = 0


class VenueSplitBucket(BaseModel):
    wins: int
    draws: int
    losses: int
    games_played: int
    points: float
    points_per_game: float


class VenueSplitRow(BaseModel):
    member_id: UUID
    display_name: str
    team_id: UUID | None = None
    team_name: str | None = None
    home: VenueSplitBucket
    away: VenueSplitBucket


class MemberHighlightsResponse(BaseModel):
    member_id: UUID
    display_name: str
    best_matchweek: dict[str, Any] | None = None
    worst_matchweek: dict[str, Any] | None = None
    biggest_upset: dict[str, Any] | None = None
    top_club: dict[str, Any] | None = None


class MatchEventRow(BaseModel):
    id: UUID
    team_id: UUID | None = None
    event_type: str
    points: float
    metadata: dict[str, Any] | None = None


class MatchEventsResponse(BaseModel):
    match_id: UUID
    kickoff_at: str
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int | None = None
    away_goals: int | None = None
    snapshot_id: UUID | None = None
    events: list[MatchEventRow] = Field(default_factory=list)
