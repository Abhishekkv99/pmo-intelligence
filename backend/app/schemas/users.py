import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

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


class RoleGrant(BaseModel):
    """Give ``email`` a role; a user who has never signed in is created."""

    email: EmailStr
    role: Role


class RoleChange(BaseModel):
    """The user's new role, or ``null`` to remove it (and end their sessions)."""

    role: Role | None


class RoleChangeResult(BaseModel):
    user: UserListItem
    # What changed, in words: sessions ended, a bootstrap-admin warning.
    message: str
