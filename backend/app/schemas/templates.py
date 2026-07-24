from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import IdSchema


class TemplateCreate(BaseModel):
    key: str
    label: str
    draft_style: str = "linear"
    preassign_mode: str = "none"
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


class TemplateResponse(IdSchema):
    key: str
    label: str
    draft_style: str
    preassign_mode: str
    result_points: dict[str, Any]
    upset_rules: dict[str, Any]
    leaderboard_phases: list[Any]
    leaderboard_tiebreaks: list[Any]
    buy_in: Decimal
    payouts: list[Any]
    roster_slots: list[Any]
    pool_definitions: list[Any]
    bonus_types: list[Any]


class TemplateUpdate(BaseModel):
    label: str | None = None
    draft_style: str | None = None
    preassign_mode: str | None = None
    result_points: dict[str, Any] | None = None
    upset_rules: dict[str, Any] | None = None
    leaderboard_phases: list[Any] | None = None
    leaderboard_tiebreaks: list[Any] | None = None
    buy_in: Decimal | None = None
    payouts: list[Any] | None = None
    roster_slots: list[Any] | None = None
    pool_definitions: list[Any] | None = None
    bonus_types: list[Any] | None = None
