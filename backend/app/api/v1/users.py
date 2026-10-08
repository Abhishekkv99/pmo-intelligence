"""Users and their roles, for the admin pages.

Listing users is for the global roles: the register's people pickers use it,
and the Users and roles tab shows it.
"""

from fastapi import APIRouter, Depends

from app.dependencies import DbSession, require_roles
from app.models.enums import Role
from app.schemas.users import UserListItem
from app.services.user_roles import UserRoleService

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


@router.get("", response_model=list[UserListItem], dependencies=ADMINS)
async def list_users(db: DbSession) -> list[UserListItem]:
    return [
        UserListItem.model_validate(user)
        for user in await UserRoleService(db).list_users()
    ]
