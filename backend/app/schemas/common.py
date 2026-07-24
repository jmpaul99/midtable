from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    dev_tools_enabled: bool = False


class MessageResponse(BaseModel):
    detail: str


class IdSchema(ORMModel):
    """Expose public_id as API `id`."""

    id: UUID = Field(validation_alias=AliasChoices("public_id", "id"))
