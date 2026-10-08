"""Users and their roles: the Admin "Users and roles" tab.

For the global roles (PMO manager, admin). A role is what lets someone sign
in, so granting one creates the user by email, and removing one ends their
sessions. The last active PMO manager keeps the role (409).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.dependencies import DbSession, require_roles
from app.models.enums import Role
from app.schemas.users import RoleChange, RoleChangeResult, RoleGrant, UserListItem
from app.services.user_roles import RoleChangeRefusedError, UserRoleService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


@router.get("", response_model=list[UserListItem], dependencies=ADMINS)
async def list_users(db: DbSession) -> list[UserListItem]:
    return [
        UserListItem.model_validate(user)
        for user in await UserRoleService(db).list_users()
    ]


@router.post("", response_model=RoleChangeResult, dependencies=ADMINS)
async def grant_role(body: RoleGrant, db: DbSession) -> RoleChangeResult:
    """Give an address a role; creates the user if they have never signed in."""
    return await _set_role(db, str(body.email), body.role)


@router.patch("/{user_id}", response_model=RoleChangeResult, dependencies=ADMINS)
async def change_role(
    user_id: uuid.UUID, body: RoleChange, db: DbSession
) -> RoleChangeResult:
    """Change a user's role, or remove it with ``null``."""
    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))
    return await _set_role(db, user.email, body.role)


async def _set_role(
    db: AsyncSession, email: str, role: Role | None
) -> RoleChangeResult:
    service = UserRoleService(db)
    try:
        message = await service.set_role(email, role)
    except RoleChangeRefusedError as exc:
        raise ConflictError(str(exc)) from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    user = await UserRepository(db).get_by_email(email.strip().lower())
    if user is None:  # set_role always leaves a row behind when given a role
        raise NotFoundError("User", email)
    return RoleChangeResult(
        user=UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=Role(user.role) if user.role else None,
            is_active=user.is_active,
            signed_in_with_microsoft=user.entra_oid is not None,
        ),
        message=message,
    )
