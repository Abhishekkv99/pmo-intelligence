import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.access_log import AccessLog


class AccessLogRepository(BaseRepository[AccessLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AccessLog)

    async def record(
        self, user_id: uuid.UUID, placement_id: uuid.UUID, route: str
    ) -> AccessLog:
        """Add one read of ``placement_id`` by ``user_id``; the request commits."""
        return await self.create(
            user_id=user_id, placement_id=placement_id, route=route
        )
