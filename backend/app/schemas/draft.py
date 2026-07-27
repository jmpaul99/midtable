from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import IdSchema


class DraftPickRequest(BaseModel):
    team_id: UUID
    idempotency_key: str | None = None
    expected_version: int | None = None


class DraftPickResponse(IdSchema):
    pick_number: int
    round_number: int
    member_id: UUID
    team_id: UUID
    pool_id: UUID
    team_name: str | None = None
    crest_url: str | None = None


class DraftStateResponse(BaseModel):
    id: UUID
    status: str
    current_pick_number: int
    current_round: int = 1
    on_clock_member_id: UUID | None = None
    current_member_id: UUID | None = None
    league_status: str
    version: int = 1
    pick_deadline_at: datetime | None = None
    pick_timer_seconds: int | None = None
    draft_scheduled_at: datetime | None = None
    picks: list[DraftPickResponse] = Field(default_factory=list)
