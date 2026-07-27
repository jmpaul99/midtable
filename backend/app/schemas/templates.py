from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import IdSchema, ORMModel
from app.services.preassign import validate_preassign_pair


class TemplateCreate(BaseModel):
    label: str
    draft_style: str = "linear"
    preassign_mode: Literal["off", "optional", "required"] = "off"
    preassign_count: int = Field(default=1, ge=0)
    result_points: dict[str, Any] = Field(default_factory=lambda: {"win": 3, "draw": 1})
    upset_rules: dict[str, Any] = Field(default_factory=dict)
    leaderboard_phases: list[Any] = Field(default_factory=list)
    leaderboard_tiebreaks: list[Any] = Field(
        default_factory=lambda: [{"metric": "total_points", "direction": "desc"}]
    )
    buy_in: Decimal = Decimal("0")
    payouts: list[Any] = Field(default_factory=list)
    roster_slots: list[Any] = Field(default_factory=list)
    pool_definitions: list[Any] = Field(default_factory=list)
    bonus_types: list[Any] = Field(default_factory=list)
    roster_club_order: Literal["draft", "competition"] = "draft"
    max_members: int | None = Field(default=None, ge=2, le=100)
    featured: bool = False
    made_by_staff: bool = False

    @model_validator(mode="after")
    def reject_required_with_zero(self) -> Self:
        validate_preassign_pair(self.preassign_mode, self.preassign_count)
        return self


class TemplateResponse(IdSchema):
    key: str
    label: str
    draft_style: str
    preassign_mode: str
    preassign_count: int = 1
    result_points: dict[str, Any]
    upset_rules: dict[str, Any]
    leaderboard_phases: list[Any]
    leaderboard_tiebreaks: list[Any]
    buy_in: Decimal
    payouts: list[Any]
    roster_slots: list[Any]
    pool_definitions: list[Any]
    bonus_types: list[Any]
    roster_club_order: Literal["draft", "competition"] = "draft"
    max_members: int | None = None
    featured: bool = False
    made_by_staff: bool = False
    created_by_id: UUID | None = None
    can_edit: bool = False


class TemplateUpdate(BaseModel):
    label: str | None = None
    draft_style: str | None = None
    preassign_mode: Literal["off", "optional", "required"] | None = None
    preassign_count: int | None = Field(default=None, ge=0)
    result_points: dict[str, Any] | None = None
    upset_rules: dict[str, Any] | None = None
    leaderboard_phases: list[Any] | None = None
    leaderboard_tiebreaks: list[Any] | None = None
    buy_in: Decimal | None = None
    payouts: list[Any] | None = None
    roster_slots: list[Any] | None = None
    pool_definitions: list[Any] | None = None
    bonus_types: list[Any] | None = None
    roster_club_order: Literal["draft", "competition"] | None = None
    max_members: int | None = Field(default=None, ge=2, le=100)
    featured: bool | None = None
    made_by_staff: bool | None = None


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    total: int
    page: int
    page_size: int
    competition_codes: list[str] = Field(default_factory=list)


class RecentTemplateUsage(ORMModel):
    template: TemplateResponse
    league_id: UUID
    league_name: str
    used_at: datetime
