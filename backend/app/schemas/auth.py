from uuid import UUID

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    auth_user_id: UUID | None = None
