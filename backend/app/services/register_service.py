"""The placement register: consultants, clients, projects and placements.

Owned here (BACKLOG #3): PMO managers and admins create and edit it on the
admin pages, and seed it once from a CSV (``register_import``). The rules in
this module apply to both:

- a client is unique by its normalised name, a consultant by email, a project
  by (client, name), a placement by (consultant, project, start date);
- people named on a project or placement (tech lead, PS, SME) must be active
  users who hold a role, because being named is what gives a scoped user read
  access to the placement;
- nothing is deleted: a placement ends by status, a consultant leaves by status.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.client_repo import ClientRepository
from app.db.repositories.consultant_repo import ConsultantRepository
from app.db.repositories.placement_repo import PlacementRepository, PlacementRow
from app.db.repositories.project_repo import ProjectRepository
from app.db.repositories.user_repo import UserRepository
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User
from app.schemas.register import (
    ClientCreate,
    ClientUpdate,
    ConsultantCreate,
    ConsultantUpdate,
    PlacementCreate,
    PlacementUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError


def normalize_name(name: str) -> str:
    """The dedup form of a name: trimmed, spaces collapsed, case-folded."""
    return " ".join(name.split()).casefold()


def tidy(name: str) -> str:
    """A name as stored: trimmed, inner spaces collapsed, case kept."""
    return " ".join(name.split())


@dataclass(frozen=True)
class ProjectRow:
    project: Project
    client: Client
    tech_lead: User | None


class RegisterService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.consultants = ConsultantRepository(session)
        self.clients = ClientRepository(session)
        self.projects = ProjectRepository(session)
        self.placements = PlacementRepository(session)
        self.users = UserRepository(session)

    # --- People -----------------------------------------------------------

    async def named_person(self, user_id: uuid.UUID | None, field: str) -> User | None:
        """The user ``user_id`` refers to, who must be active and hold a role."""
        if user_id is None:
            return None
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active or user.role is None:
            raise ValidationError(f"{field}: no active user with a role has that id")
        return user

    # --- Consultants ------------------------------------------------------

    async def list_consultants(self) -> list[Consultant]:
        return await self.consultants.list_by_name()

    async def create_consultant(self, data: ConsultantCreate) -> Consultant:
        email = str(data.email).lower() if data.email else None
        if email:
            await self._assert_consultant_email_free(email, None)
        return await self.consultants.create(
            full_name=tidy(data.full_name),
            email=email,
            phone=data.phone or None,
            skills=data.skills,
            status=data.status.value,
        )

    async def update_consultant(
        self, consultant_id: uuid.UUID, data: ConsultantUpdate
    ) -> Consultant:
        consultant = await self._consultant(consultant_id)
        fields = data.model_dump(exclude_unset=True)
        _refuse_null(fields, ("full_name", "status", "skills"))
        if "full_name" in fields:
            consultant.full_name = tidy(fields["full_name"])
        if "email" in fields:
            email = str(fields["email"]).lower() if fields["email"] else None
            if email:
                await self._assert_consultant_email_free(email, consultant.id)
            consultant.email = email
        if "phone" in fields:
            consultant.phone = fields["phone"] or None
        if "skills" in fields:
            consultant.skills = fields["skills"]
        if "status" in fields:
            consultant.status = fields["status"].value
        await self.session.flush()
        # The flush expires the server-set updated_at; reload it here, since
        # the response reads it and a lazy load cannot run under async
        await self.session.refresh(consultant)
        return consultant

    async def _assert_consultant_email_free(
        self, email: str, consultant_id: uuid.UUID | None
    ) -> None:
        existing = await self.consultants.get_by_email(email)
        if existing is not None and existing.id != consultant_id:
            raise ConflictError(f"A consultant with email {email} already exists")

    async def _consultant(self, consultant_id: uuid.UUID) -> Consultant:
        consultant = await self.consultants.get_by_id(consultant_id)
        if consultant is None:
            raise NotFoundError("Consultant", str(consultant_id))
        return consultant

    # --- Clients ----------------------------------------------------------

    async def list_clients(self) -> list[Client]:
        return await self.clients.list_by_name()

    async def create_client(self, data: ClientCreate) -> Client:
        normalized = normalize_name(data.name)
        await self._assert_client_name_free(normalized, None)
        return await self.clients.create(
            name=tidy(data.name),
            normalized_name=normalized,
            industry=data.industry or None,
        )

    async def update_client(self, client_id: uuid.UUID, data: ClientUpdate) -> Client:
        client = await self._client(client_id)
        fields = data.model_dump(exclude_unset=True)
        _refuse_null(fields, ("name",))
        if "name" in fields:
            normalized = normalize_name(fields["name"])
            await self._assert_client_name_free(normalized, client.id)
            client.name = tidy(fields["name"])
            client.normalized_name = normalized
        if "industry" in fields:
            client.industry = fields["industry"] or None
        await self.session.flush()
        # The flush expires the server-set updated_at; reload it here, since
        # the response reads it and a lazy load cannot run under async
        await self.session.refresh(client)
        return client

    async def _assert_client_name_free(
        self, normalized: str, client_id: uuid.UUID | None
    ) -> None:
        existing = await self.clients.get_by_normalized_name(normalized)
        if existing is not None and existing.id != client_id:
            raise ConflictError(f"A client named {existing.name} already exists")

    async def _client(self, client_id: uuid.UUID) -> Client:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            raise NotFoundError("Client", str(client_id))
        return client

    # --- Projects ---------------------------------------------------------

    async def list_projects(self) -> list[ProjectRow]:
        pairs = await self.projects.list_with_clients()
        lead_ids = {p.tech_lead_user_id for p, _ in pairs if p.tech_lead_user_id}
        leads: dict[uuid.UUID | None, User] = {
            u.id: u for u in await self.users.get_by_ids(lead_ids)
        }
        return [
            ProjectRow(project, client, leads.get(project.tech_lead_user_id))
            for project, client in pairs
        ]

    async def project_row(self, project: Project) -> ProjectRow:
        client = await self._client(project.client_id)
        lead = (
            await self.users.get_by_id(project.tech_lead_user_id)
            if project.tech_lead_user_id
            else None
        )
        return ProjectRow(project, client, lead)

    async def create_project(self, data: ProjectCreate) -> Project:
        client = await self._referenced_client(data.client_id)
        await self._assert_project_name_free(client.id, data.name, None)
        await self.named_person(data.tech_lead_user_id, "tech_lead_user_id")
        return await self.projects.create(
            client_id=client.id,
            name=tidy(data.name),
            client_manager_name=data.client_manager_name or None,
            tech_lead_user_id=data.tech_lead_user_id,
            start_date=data.start_date,
        )

    async def update_project(
        self, project_id: uuid.UUID, data: ProjectUpdate
    ) -> Project:
        project = await self.projects.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project", str(project_id))
        fields = data.model_dump(exclude_unset=True)
        _refuse_null(fields, ("client_id", "name"))
        client_id = fields.get("client_id", project.client_id)
        name = fields.get("name", project.name)
        if "client_id" in fields:
            await self._referenced_client(client_id)
        if "client_id" in fields or "name" in fields:
            await self._assert_project_name_free(client_id, name, project.id)
            project.client_id = client_id
            project.name = tidy(name)
        if "client_manager_name" in fields:
            project.client_manager_name = fields["client_manager_name"] or None
        if "tech_lead_user_id" in fields:
            await self.named_person(fields["tech_lead_user_id"], "tech_lead_user_id")
            project.tech_lead_user_id = fields["tech_lead_user_id"]
        if "start_date" in fields:
            project.start_date = fields["start_date"]
        await self.session.flush()
        # The flush expires the server-set updated_at; reload it here, since
        # the response reads it and a lazy load cannot run under async
        await self.session.refresh(project)
        return project

    async def _assert_project_name_free(
        self, client_id: uuid.UUID, name: str, project_id: uuid.UUID | None
    ) -> None:
        existing = await self.projects.get_by_client_and_name(client_id, name)
        if existing is not None and existing.id != project_id:
            raise ConflictError(
                f"This client already has a project named {existing.name}"
            )

    async def _referenced_client(self, client_id: uuid.UUID) -> Client:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            raise ValidationError("client_id: no client has that id")
        return client

    # --- Placements -------------------------------------------------------

    async def list_placements(self) -> list[PlacementRow]:
        return await self.placements.list_rows()

    async def placement_row(self, placement_id: uuid.UUID) -> PlacementRow:
        row = await self.placements.get_row(placement_id)
        if row is None:
            raise NotFoundError("Placement", str(placement_id))
        return row

    async def create_placement(self, data: PlacementCreate) -> Placement:
        await self._referenced_consultant(data.consultant_id)
        await self._referenced_project(data.project_id)
        _assert_dates(data.start_date, data.expected_end_date)
        await self._assert_placement_free(
            data.consultant_id, data.project_id, data.start_date, None
        )
        await self.named_person(data.ps_user_id, "ps_user_id")
        await self.named_person(data.sme_user_id, "sme_user_id")
        return await self.placements.create(
            consultant_id=data.consultant_id,
            project_id=data.project_id,
            start_date=data.start_date,
            expected_end_date=data.expected_end_date,
            extension_status=data.extension_status.value,
            rate_band=data.rate_band or None,
            ps_user_id=data.ps_user_id,
            sme_user_id=data.sme_user_id,
            status=data.status.value,
            ended_reason=data.ended_reason or None,
        )

    async def update_placement(
        self, placement: Placement, data: PlacementUpdate
    ) -> Placement:
        fields = data.model_dump(exclude_unset=True)
        _refuse_null(
            fields,
            ("consultant_id", "project_id", "start_date", "extension_status", "status"),
        )
        consultant_id = fields.get("consultant_id", placement.consultant_id)
        project_id = fields.get("project_id", placement.project_id)
        start_date = fields.get("start_date", placement.start_date)
        end_date = fields.get("expected_end_date", placement.expected_end_date)
        if "consultant_id" in fields:
            await self._referenced_consultant(consultant_id)
        if "project_id" in fields:
            await self._referenced_project(project_id)
        _assert_dates(start_date, end_date)
        if fields.keys() & {"consultant_id", "project_id", "start_date"}:
            await self._assert_placement_free(
                consultant_id, project_id, start_date, placement.id
            )
        for field in ("ps_user_id", "sme_user_id"):
            if field in fields:
                await self.named_person(fields[field], field)
        for key, value in fields.items():
            if key in ("extension_status", "status"):
                value = value.value
            elif key in ("rate_band", "ended_reason"):
                value = value or None
            setattr(placement, key, value)
        await self.session.flush()
        return placement

    async def _assert_placement_free(
        self,
        consultant_id: uuid.UUID,
        project_id: uuid.UUID,
        start_date: date,
        placement_id: uuid.UUID | None,
    ) -> None:
        existing = await self.placements.get_by_key(
            consultant_id, project_id, start_date
        )
        if existing is not None and existing.id != placement_id:
            raise ConflictError(
                "This consultant already has a placement on this project "
                "starting that day"
            )

    async def _referenced_consultant(self, consultant_id: uuid.UUID) -> Consultant:
        consultant = await self.consultants.get_by_id(consultant_id)
        if consultant is None:
            raise ValidationError("consultant_id: no consultant has that id")
        return consultant

    async def _referenced_project(self, project_id: uuid.UUID) -> Project:
        project = await self.projects.get_by_id(project_id)
        if project is None:
            raise ValidationError("project_id: no project has that id")
        return project


def _assert_dates(start: date, end: date | None) -> None:
    if end is not None and end < start:
        raise ValidationError("expected_end_date is before start_date")


def _refuse_null(fields: dict[str, Any], required: tuple[str, ...]) -> None:
    """A PATCH may clear a nullable field with null, never a required one."""
    for name in required:
        if name in fields and fields[name] is None:
            raise ValidationError(f"{name} cannot be empty")
