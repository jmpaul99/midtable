from decimal import Decimal
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, model_validator


class BonusTypeCreate(BaseModel):
    key: str
    label: str
    default_points: Decimal
    sort_order: int = 0
    include_in_phases: list[str] | None = None


class BonusTypeUpdate(BaseModel):
    label: str | None = None
    default_points: Decimal | None = None
    sort_order: int | None = None
    include_in_phases: list[str] | None = None


class ManualBonusCreate(BaseModel):
    target: Literal["team", "match", "manager"] = "team"
    team_id: UUID | None = None
    match_id: UUID | None = None
    member_id: UUID | None = None
    bonus_type_id: UUID
    points: Decimal | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_target_fields(self) -> "ManualBonusCreate":
        if self.target == "team":
            if self.team_id is None:
                raise ValueError("team_id is required for team bonuses")
            if self.match_id is not None or self.member_id is not None:
                raise ValueError("match_id and member_id must be omitted for team bonuses")
        elif self.target == "match":
            if self.team_id is None or self.match_id is None:
                raise ValueError("team_id and match_id are required for match bonuses")
            if self.member_id is not None:
                raise ValueError("member_id must be omitted for match bonuses")
        elif self.target == "manager":
            if self.member_id is None:
                raise ValueError("member_id is required for manager bonuses")
            if self.team_id is not None or self.match_id is not None:
                raise ValueError("team_id and match_id must be omitted for manager bonuses")
        return self


class BonusTypeResponse(BaseModel):
    id: UUID
    key: str
    label: str
    default_points: float
    sort_order: int
    include_in_phases: list[Any] | None = None


class ManualBonusResponse(BaseModel):
    id: UUID
    target: str
    team_id: UUID | None = None
    team_name: str | None = None
    match_id: UUID | None = None
    match_label: str | None = None
    member_id: UUID | None = None
    display_name: str | None = None
    bonus_type: str | None = None
    points: float
    reason: str | None = None
    awarded_at: datetime | None = None
    revoked_at: datetime | None = None


class ManualBonusAwardResponse(BaseModel):
    id: UUID
    points: float
    target: str
