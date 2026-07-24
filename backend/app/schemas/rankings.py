from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import IdSchema


class RankingListCreate(BaseModel):
    key: str
    label: str
    source: str = "manual"
    as_of: date | None = None


class RankingImportRequest(BaseModel):
    text: str
    # Optional explicit mappings: rank -> team public_id
    mappings: dict[int, UUID] | None = None


class RankingListResponse(IdSchema):
    key: str
    label: str
    source: str
    as_of: date | None = None
    locked: bool


class RankingParseResponse(BaseModel):
    rows: list[dict] = Field(default_factory=list)
