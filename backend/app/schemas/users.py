import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import Role


class UserListItem(BaseModel):
    """A user as the admin pages list them; no tokens, no Entra ids."""

    id: uuid.UUID
    email: str
    full_name: str
    role: Role | None
    is_active: bool
    # False until the user's first sign-in links the Entra account.
    signed_in_with_microsoft: bool

    model_config = ConfigDict(from_attributes=True)
