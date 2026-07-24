from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PoolConfig(APIModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    provider_competition_code: str
    slots_per_member: int = Field(gt=0)
    slot_label: str = Field(min_length=1)
    scoring_enabled: bool = True


class LeaderboardRungConfig(APIModel):
    metric: Literal[
        "total_points",
        "event_points",
        "event_count",
        "bonus_points",
        "bonus_count",
    ]
    event_types: list[str] = Field(default_factory=list)
    bonus_type_keys: list[str] = Field(default_factory=list)
    direction: Literal["desc", "asc"] = "desc"

    @model_validator(mode="after")
    def validate_selector(self) -> "LeaderboardRungConfig":
        event_metric = self.metric in {"event_points", "event_count"}
        bonus_metric = self.metric in {"bonus_points", "bonus_count"}
        if event_metric != bool(self.event_types):
            raise ValueError("event metrics require event_types and other metrics forbid them")
        if bonus_metric != bool(self.bonus_type_keys):
            raise ValueError("bonus metrics require bonus_type_keys and other metrics forbid them")
        if len(self.event_types) != len(set(self.event_types)):
            raise ValueError("event_types cannot repeat")
        if len(self.bonus_type_keys) != len(set(self.bonus_type_keys)):
            raise ValueError("bonus_type_keys cannot repeat")
        return self


class TemplateWrite(APIModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    provider: str = "football-data.org"
    provider_competition_code: str
    default_team_count: int = Field(gt=1)
    default_roster_size: int = Field(gt=0)
    pools: list[PoolConfig] = Field(min_length=1)
    scoring: dict[str, Any]
    phases: list[dict[str, Any]] = Field(default_factory=list)
    leaderboard_tiebreaks: list[LeaderboardRungConfig] = Field(
        default_factory=lambda: [
            LeaderboardRungConfig(metric="total_points"),
            LeaderboardRungConfig(metric="event_points", event_types=["upset"]),
            LeaderboardRungConfig(metric="event_count", event_types=["win"]),
        ]
    )
    bonuses: dict[str, Decimal] = Field(default_factory=dict)
    payouts: list[dict[str, Any]] = Field(default_factory=list)
    draft: dict[str, Any] = Field(default_factory=lambda: {"format": "linear"})
    is_active: bool = True

    @field_validator("leaderboard_tiebreaks", mode="before")
    @classmethod
    def parse_legacy_tiebreaks(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        legacy = {
            "total_points": {"metric": "total_points", "direction": "desc"},
            "upset_points": {
                "metric": "event_points",
                "event_types": ["__configured_upsets__"],
                "direction": "desc",
            },
            "win_count": {
                "metric": "event_count",
                "event_types": ["win"],
                "direction": "desc",
            },
        }
        return [legacy.get(item, item) if isinstance(item, str) else item for item in value]

    @model_validator(mode="after")
    def validate_configuration(self) -> "TemplateWrite":
        if sum(pool.slots_per_member for pool in self.pools) != self.default_roster_size:
            raise ValueError("pool slots must equal default_roster_size")
        if self.draft.get("format", "linear") not in {"linear", "snake"}:
            raise ValueError("draft format must be linear or snake")
        if not self.leaderboard_tiebreaks:
            raise ValueError("at least one leaderboard tiebreak rung is required")
        result_keys = set(self.scoring.get("result_points", {}))
        thresholds = self.scoring.get("upset", {}).get("thresholds", [])
        upset_keys = {
            str(item["key"]) for item in thresholds if isinstance(item, dict) and item.get("key")
        }
        if thresholds and not upset_keys:
            upset_keys.add("upset")
        event_keys = result_keys | upset_keys
        bonus_keys = set(self.bonuses)
        normalized: list[LeaderboardRungConfig] = []
        for rung in self.leaderboard_tiebreaks:
            if rung.event_types == ["__configured_upsets__"]:
                rung = rung.model_copy(update={"event_types": sorted(upset_keys or {"upset"})})
            unknown_events = set(rung.event_types) - event_keys
            unknown_bonuses = set(rung.bonus_type_keys) - bonus_keys
            if unknown_events:
                raise ValueError(
                    f"leaderboard tiebreak references unknown event keys: {sorted(unknown_events)}"
                )
            if unknown_bonuses:
                raise ValueError(
                    f"leaderboard tiebreak references unknown bonus keys: {sorted(unknown_bonuses)}"
                )
            normalized.append(rung)
        self.leaderboard_tiebreaks = normalized
        return self


class TemplateOut(TemplateWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime


class DuplicateTemplate(APIModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)


class LeagueCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    template_id: UUID
    season: str = Field(min_length=1, max_length=20)
    max_members: int = Field(ge=2, le=100)
    visibility: Literal["private", "unlisted", "public"] = "private"
    provider_params: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class LeagueSummary(APIModel):
    id: UUID
    name: str
    slug: str
    status: str
    visibility: str
    max_members: int
    role: str
    season: str
    template_id: UUID


class LeagueDetail(LeagueSummary):
    current_member_id: UUID
    settings: dict[str, Any]
    pools: list[dict[str, Any]]
    members: list[dict[str, Any]]
    phases: list[dict[str, Any]]
    bonus_type_keys: list[str] = Field(default_factory=list)
    provider_params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class InviteCreate(APIModel):
    email: EmailStr
    commissioner: bool = False
    expires_in_hours: int = Field(default=168, ge=1, le=2160)


class InviteOut(APIModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    token: str | None = None


class InviteAccept(APIModel):
    token: str = Field(min_length=20)
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class DraftOrderWrite(APIModel):
    member_ids: list[UUID] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_members(self) -> "DraftOrderWrite":
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("draft order contains duplicates")
        return self


class PreassignmentWrite(APIModel):
    member_id: UUID
    team_id: UUID
    slot_number: int = Field(gt=0)
    keeper: bool = False


class DraftStart(APIModel):
    format: Literal["linear", "snake"] | None = None


class DraftPickCreate(APIModel):
    team_id: UUID
    idempotency_key: UUID
    expected_version: int = Field(gt=0)


class DraftStateOut(APIModel):
    id: UUID
    pool_id: UUID
    status: str
    current_pick_number: int
    current_round: int
    current_member_id: UUID | None
    version: int
    picks: list[dict[str, Any]] = Field(default_factory=list)


class RosterCorrection(APIModel):
    member_id: UUID
    team_id: UUID
    slot_number: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class PickCorrection(APIModel):
    pick_id: UUID
    team_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class BootstrapRequest(APIModel):
    provider_params: dict[str, Any] = Field(default_factory=dict)


class ReadinessOut(APIModel):
    ready: bool
    errors: list[str]
    warnings: list[str]


class SyncRequest(APIModel):
    date_from: datetime | None = None
    date_to: datetime | None = None
    statuses: list[str] = Field(default_factory=list)


class SyncOut(APIModel):
    status: str
    synced_matches: int = 0
    changed_results: int = 0
    affected_matches: int = 0
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: datetime | None = None


class BonusWrite(APIModel):
    team_id: UUID
    match_id: UUID | None = None
    bonus_type: str = Field(min_length=1, max_length=80)
    phase: str = Field(default="overall", min_length=1, max_length=80)
    points: Decimal
    reason: str = Field(min_length=1, max_length=500)


class BonusOut(BonusWrite):
    id: UUID
    member_id: UUID | None = None
    display_name: str | None = None
    awarded_at: datetime
    revoked_at: datetime | None


class RankingListCreate(APIModel):
    pool_id: UUID
    name: str = Field(min_length=1, max_length=160)


class RankingImport(APIModel):
    member_id: UUID
    text: str = Field(min_length=1)
    delimiter: str | None = None
    has_header: bool = False
    team_column: int = Field(default=0, ge=0)
    rank_column: int | None = Field(default=None, ge=0)


class RankingListOut(APIModel):
    id: UUID
    pool_id: UUID
    name: str
    status: str
    locked_at: datetime | None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class StandingsEntry(APIModel):
    member_id: UUID
    display_name: str
    rank: int
    total_points: Decimal
    upset_points: Decimal
    win_count: int
    payout: Decimal = Decimal(0)
    metric_values: list[dict[str, Any]] = Field(default_factory=list)


class PhaseMetadata(APIModel):
    key: str
    name: str
    matchweek_range: list[int] | None = None
    stage_in: list[str] | None = None
    matching_matches: int
    finished_matches: int
    remaining_matches: int
    is_final: bool


class StandingsOut(APIModel):
    phase: PhaseMetadata
    entries: list[StandingsEntry]


class PoolTeamOut(APIModel):
    id: UUID
    name: str
    crest_url: str | None = None
    provider_team_id: str
    drafted: bool
    current_owner: dict[str, Any] | None = None
    available: bool


class ProviderParamsWrite(APIModel):
    league: dict[str, Any] = Field(default_factory=dict)
    pools: dict[UUID, dict[str, Any]] = Field(default_factory=dict)


class AuditEntry(APIModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    created_at: datetime


class Message(APIModel):
    detail: str
