from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.register import Client


class ClientRepository(BaseRepository[Client]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Client)

    async def list_by_name(self) -> list[Client]:
        stmt = select(Client).order_by(Client.normalized_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_normalized_name(self, normalized_name: str) -> Client | None:
        stmt = select(Client).where(Client.normalized_name == normalized_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
