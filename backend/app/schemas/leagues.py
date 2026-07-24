from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import IdSchema


class LeagueCreate(BaseModel):
    name: str
    season_label: str
    template_id: UUID | None = None
    draft_style: str = "linear"
    preassign_mode: str = "none"


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


class MemberResponse(IdSchema):
    is_commissioner: bool
    draft_slot: int | None = None
    profile_id: UUID | None = None
    email: str | None = None
    display_name: str | None = None


class InviteCreate(BaseModel):
    email: str
    is_commissioner: bool = False
    draft_slot: int | None = None


class InviteResponse(IdSchema):
    email: str
    is_commissioner: bool
    draft_slot: int | None = None
    status: str


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
    scheduled_start_date: date | None = None
    scheduled_end_date: date | None = None
    force: bool = False


class LeagueSettingsUpdate(BaseModel):
    result_points: dict[str, Any] | None = None
    upset_rules: dict[str, Any] | None = None
    leaderboard_phases: list[Any] | None = None
    leaderboard_tiebreaks: list[Any] | None = None
    buy_in: Decimal | None = None
    payouts: list[Any] | None = None
