import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.register import Client, Project


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Project)

    async def list_with_clients(self) -> list[tuple[Project, Client]]:
        """Every project with its client, ordered by client then project."""
        stmt = (
            select(Project, Client)
            .join(Client, Client.id == Project.client_id)
            .order_by(Client.normalized_name, func.lower(Project.name))
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_by_client_and_name(
        self, client_id: uuid.UUID, name: str
    ) -> Project | None:
        """The client's project called ``name``, ignoring case and spacing."""
        wanted = " ".join(name.split()).lower()
        stmt = select(Project).where(
            Project.client_id == client_id,
            func.lower(func.regexp_replace(func.trim(Project.name), r"\s+", " ", "g"))
            == wanted,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
