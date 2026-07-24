from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.auth.jwt import MAX_DISPLAY_NAME_LEN
from app.schemas.common import IdSchema


class LeagueCreate(BaseModel):
    name: str
    season_label: str
    template_id: UUID | None = None
    draft_style: str = "linear"
    preassign_mode: str = "none"
    max_members: int = Field(ge=2, le=100)


class PoolResponse(IdSchema):
    key: str
    label: str
    scores_match_results: bool
    slot_count: int
    sort_order: int = 0
    provider: str
    competition_code: str | None = None
    season_year: int | None = None
    tie_break_order: list[Any] = Field(default_factory=list)


class MemberResponse(IdSchema):
    is_commissioner: bool
    draft_slot: int | None = None
    profile_id: UUID | None = None
    email: str | None = None
    display_name: str | None = None
    team_name: str | None = None
    role: str = "member"


class MemberSelfUpdate(BaseModel):
    """Update the current user's membership in a league (fantasy team name)."""

    team_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME_LEN)

    @field_validator("team_name")
    @classmethod
    def normalize_team_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            return None
        if len(name) > MAX_DISPLAY_NAME_LEN:
            raise ValueError(f"Team name must be at most {MAX_DISPLAY_NAME_LEN} characters")
        return name


class MemberAdminUpdate(BaseModel):
    """Commissioner update of another (or self) membership role."""

    is_commissioner: bool


class PhaseResponse(BaseModel):
    key: str
    name: str
    matchweek_range: list[int] | None = None
    stage_in: list[str] | None = None
    is_final: bool = False


class LeagueResponse(IdSchema):
    name: str
    season_label: str
    status: str
    draft_style: str
    preassign_mode: str
    result_points: dict[str, Any]
    upset_rules: dict[str, Any]
    leaderboard_phases: list[Any]
    leaderboard_tiebreaks: list[Any]
    buy_in: Decimal
    payouts: list[Any]
    scheduled_start_date: date | None = None
    scheduled_end_date: date | None = None
    template_id: UUID | None = None
    max_members: int | None = None
    role: str | None = None
    my_rank: int | None = None
    member_count: int | None = None
    my_points: float | None = None
    my_draft_slot: int | None = None
    has_scored: bool = False


class LeagueDetailResponse(LeagueResponse):
    current_member_id: UUID | None = None
    role: str = "member"
    settings: dict[str, Any] = Field(default_factory=dict)
    members: list[MemberResponse] = Field(default_factory=list)
    pools: list[PoolResponse] = Field(default_factory=list)
    phases: list[PhaseResponse] = Field(default_factory=list)
    bonus_type_keys: list[str] = Field(default_factory=list)
    provider_params: dict[str, Any] = Field(default_factory=dict)


class InviteCreate(BaseModel):
    email: str
    is_commissioner: bool = False
    draft_slot: int | None = None


class InviteResponse(IdSchema):
    email: str
    is_commissioner: bool
    draft_slot: int | None = None
    status: str
    token: str | None = None
    role: str = "member"


class InviteAcceptRequest(BaseModel):
    token: str


class InviteAcceptResponse(MemberResponse):
    league_id: UUID


class DraftOrderUpdate(BaseModel):
    member_ids: list[UUID] = Field(min_length=1)


class PreassignRequest(BaseModel):
    member_id: UUID
    team_id: UUID
    pool_id: UUID


class BootstrapSeasonRequest(BaseModel):
    template_key: str = "premier_league"
    name: str
    season_label: str
    pool_provider_params: list[dict[str, Any]]
    max_members: int | None = Field(default=None, ge=2, le=100)
    scheduled_start_date: date | None = None
    scheduled_end_date: date | None = None
    force: bool = False


class PoolSettingsPatch(BaseModel):
    """Commissioner updates for an existing league competition (matched by public id)."""

    id: UUID
    sort_order: int | None = Field(default=None, ge=0)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    scores_match_results: bool | None = None
    slot_count: int | None = Field(default=None, ge=1, le=50)

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Value cannot be empty")
        return trimmed


class LeagueSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    season_label: str | None = Field(default=None, min_length=1, max_length=40)
    result_points: dict[str, Any] | None = None
    upset_rules: dict[str, Any] | None = None
    leaderboard_phases: list[Any] | None = None
    leaderboard_tiebreaks: list[Any] | None = None
    buy_in: Decimal | None = None
    payouts: list[Any] | None = None
    max_members: int | None = Field(default=None, ge=2, le=100)
    pools: list[PoolSettingsPatch] | None = None

    @field_validator("name", "season_label")
    @classmethod
    def trim_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Value cannot be empty")
        return trimmed



class BootstrapTeamsRequest(BaseModel):
    """Optional per-pool provider overrides when loading teams into existing pools."""

    pool_provider_params: list[dict[str, Any]] = Field(default_factory=list)


class BootstrapTeamsResponse(BaseModel):
    created_teams: int
    linked: int
    skipped_existing: int
    pools: list[dict[str, Any]] = Field(default_factory=list)


class RecomputeResponse(BaseModel):
    scored: int = 0
    cascaded: int = 0
    skipped_missing_snapshot: int = 0
    finished_matches: int = 0


class PoolTeamResponse(IdSchema):
    name: str
    crest_url: str | None = None
    provider_team_id: str
    drafted: bool = False
    available: bool = True
    current_owner: dict[str, Any] | None = None


class RosterRowResponse(BaseModel):
    id: UUID | None = None
    member_id: UUID
    display_name: str
    pool_id: UUID
    pool_name: str
    pool_sort_order: int = 0
    slot_number: int
    team_id: UUID | None = None
    team_name: str | None = None
    crest_url: str | None = None
    acquired_via: str | None = None
    draft_pick_number: int | None = None
    points: float | None = None
    games_played: int | None = None
    points_per_game: float | None = None
    form: list[str] | None = None
    rank: int | None = None
    member_total_points: float | None = None
    member_points_per_game: float | None = None
    member_wins: int | None = None
    member_draws: int | None = None
    member_losses: int | None = None
    member_games_played: int | None = None


class RosterPatchRequest(BaseModel):
    member_id: UUID | None = None
    team_id: UUID | None = None


class MatchLogRow(BaseModel):
    id: UUID
    kickoff_at: datetime
    status: str
    scheduled_matchweek: int | None = None
    home_team_id: UUID
    away_team_id: UUID
    home_team_name: str
    away_team_name: str
    home_goals: int | None = None
    away_goals: int | None = None
    pool_id: UUID
    home_points: float | None = None
    away_points: float | None = None


class TeamFixtureRow(MatchLogRow):
    is_home: bool
    points: float | None = None
    opponent_name: str
    opponent_id: UUID
    opponent_table_position: int | None = None


class MemberClubRow(BaseModel):
    team_id: UUID
    team_name: str
    crest_url: str | None = None
    pool_id: UUID | None = None
    pool_name: str | None = None
    pool_sort_order: int = 0
    acquired_via: str | None = None
    draft_pick_number: int | None = None
    points: float = 0
    games_played: int = 0
    points_per_game: float = 0


class BonusAwardRow(BaseModel):
    id: UUID
    team_id: UUID | None = None
    team_name: str | None = None
    crest_url: str | None = None
    bonus_type: str
    bonus_type_label: str
    points: float
    reason: str | None = None
    awarded_at: datetime | None = None


class ScoringEventMatchRow(BaseModel):
    """One scoring event with enough match context for expandable breakdowns."""

    id: UUID
    event_type: str
    points: float
    match_id: UUID
    kickoff_at: datetime
    scheduled_matchweek: int | None = None
    status: str
    is_home: bool
    home_goals: int | None = None
    away_goals: int | None = None
    opponent_id: UUID
    opponent_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamDetailResponse(BaseModel):
    id: UUID
    name: str
    crest_url: str | None = None
    pool_id: UUID | None = None
    pool_name: str | None = None
    owner: dict[str, Any] | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    bonuses: list[BonusAwardRow] = Field(default_factory=list)
    scoring_events: list[ScoringEventMatchRow] = Field(default_factory=list)
    recent_matches: list[TeamFixtureRow] = Field(default_factory=list)
    upcoming_matches: list[TeamFixtureRow] = Field(default_factory=list)


class MemberDetailResponse(BaseModel):
    id: UUID
    team_name: str | None = None
    display_name: str | None = None
    draft_slot: int | None = None
    rank: int | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    clubs: list[MemberClubRow] = Field(default_factory=list)
    bonuses: list[BonusAwardRow] = Field(default_factory=list)


class SyncStatusResponse(BaseModel):
    id: UUID
    provider: str
    status: str
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    rate_limit_remaining: int | None = None
    last_error: str | None = None
    last_summary: dict[str, Any] | None = None
    in_progress: bool = False


class SnapshotAuditRow(BaseModel):
    id: UUID
    pool_id: UUID
    kickoff_at: datetime
    stale: bool
    computed_at: datetime
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ReadinessCheck(BaseModel):
    key: str
    label: str
    status: str  # ok | error | warning
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
