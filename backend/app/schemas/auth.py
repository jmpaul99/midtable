from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.auth.jwt import MAX_DISPLAY_NAME_LEN


class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    auth_user_id: UUID | None = None
    is_platform_admin: bool = False


class MeUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME_LEN)

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Display name is required")
        if len(name) > MAX_DISPLAY_NAME_LEN:
            raise ValueError(f"Display name must be at most {MAX_DISPLAY_NAME_LEN} characters")
        return name
