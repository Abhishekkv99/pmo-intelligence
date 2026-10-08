from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.register import Consultant


class ConsultantRepository(BaseRepository[Consultant]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Consultant)

    async def list_by_name(self) -> list[Consultant]:
        """Every consultant, ordered by name. Hundreds of rows at most."""
        stmt = select(Consultant).order_by(func.lower(Consultant.full_name))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_email(self, email: str) -> Consultant | None:
        """The consultant with ``email``, compared case-insensitively."""
        stmt = select(Consultant).where(
            func.lower(Consultant.email) == email.strip().lower()
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_full_name(self, full_name: str) -> list[Consultant]:
        """Consultants whose name matches, ignoring case and spacing."""
        wanted = " ".join(full_name.split()).lower()
        stmt = select(Consultant).where(
            func.lower(
                func.regexp_replace(func.trim(Consultant.full_name), r"\s+", " ", "g")
            )
            == wanted
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
