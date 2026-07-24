from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import IdSchema


class DraftPickRequest(BaseModel):
    team_id: UUID


class DraftPickResponse(IdSchema):
    pick_number: int
    round_number: int
    member_id: UUID
    team_id: UUID
    pool_id: UUID


class DraftStateResponse(BaseModel):
    id: UUID
    status: str
    current_pick_number: int
    on_clock_member_id: UUID | None = None
    league_status: str
