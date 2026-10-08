import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.user import User


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_emails(self, emails: Iterable[str]) -> list[User]:
        """Rows whose email matches any of ``emails``, case-insensitively.

        Used by the bootstrap-admin sweep, whose list is configured by hand
        and may not match the stored casing. An empty list returns no rows
        without a query.
        """
        wanted = [email.strip().lower() for email in emails if email.strip()]
        if not wanted:
            return []
        stmt = select(User).where(func.lower(User.email).in_(wanted))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: Iterable[uuid.UUID]) -> list[User]:
        """Rows with any of ``ids``; an empty set returns none without a query."""
        wanted = set(ids)
        if not wanted:
            return []
        stmt = select(User).where(User.id.in_(wanted))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_entra_oid(self, entra_oid: str) -> User | None:
        stmt = select(User).where(User.entra_oid == entra_oid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_email(self) -> list[User]:
        """Every user, ordered by email. Tens of rows, so no paging."""
        stmt = select(User).order_by(User.email)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
