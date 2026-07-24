from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class BonusTypeCreate(BaseModel):
    key: str
    label: str
    default_points: Decimal
    sort_order: int = 0
    include_in_phases: list[str] | None = None


class ManualBonusCreate(BaseModel):
    team_id: UUID
    bonus_type_id: UUID
    points: Decimal | None = None
    notes: str | None = None
