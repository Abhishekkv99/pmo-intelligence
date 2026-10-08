"""The placement register: consultants, clients, projects, placements, CSV import.

Editing the register is for the global roles (PMO manager, admin). Reading a
single placement by id is scoped like every by-id read: the people it names
may read it, anyone else gets the same 404 as for a missing placement.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.placement_repo import PlacementRow
from app.dependencies import PlacementScope, get_db, require_roles
from app.models.enums import ExtensionStatus, PlacementStatus, Role
from app.models.register import Client, Consultant
from app.models.user import User
from app.rate_limiter import limiter
from app.schemas.register import (
    ClientCreate,
    ClientResponse,
    ClientUpdate,
    ConsultantCreate,
    ConsultantResponse,
    ConsultantUpdate,
    ImportResult,
    NamedRef,
    PersonRef,
    PlacementConsultant,
    PlacementCreate,
    PlacementResponse,
    PlacementUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.register_import import MAX_BYTES, RegisterImport
from app.services.register_service import ProjectRow, RegisterService
from app.utils.exceptions import ValidationError

router = APIRouter()

EDITORS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


# --- Consultants --------------------------------------------------------------


@router.get(
    "/consultants", response_model=list[ConsultantResponse], dependencies=EDITORS
)
async def list_consultants(db: AsyncSession = Depends(get_db)) -> list[Consultant]:
    return await RegisterService(db).list_consultants()


@router.post(
    "/consultants",
    status_code=201,
    response_model=ConsultantResponse,
    dependencies=EDITORS,
)
async def create_consultant(
    body: ConsultantCreate, db: AsyncSession = Depends(get_db)
) -> Consultant:
    return await RegisterService(db).create_consultant(body)


@router.patch(
    "/consultants/{consultant_id}",
    response_model=ConsultantResponse,
    dependencies=EDITORS,
)
async def update_consultant(
    consultant_id: uuid.UUID,
    body: ConsultantUpdate,
    db: AsyncSession = Depends(get_db),
) -> Consultant:
    return await RegisterService(db).update_consultant(consultant_id, body)


# --- Clients ------------------------------------------------------------------


@router.get("/clients", response_model=list[ClientResponse], dependencies=EDITORS)
async def list_clients(db: AsyncSession = Depends(get_db)) -> list[Client]:
    return await RegisterService(db).list_clients()


@router.post(
    "/clients", status_code=201, response_model=ClientResponse, dependencies=EDITORS
)
async def create_client(
    body: ClientCreate, db: AsyncSession = Depends(get_db)
) -> Client:
    return await RegisterService(db).create_client(body)


@router.patch(
    "/clients/{client_id}", response_model=ClientResponse, dependencies=EDITORS
)
async def update_client(
    client_id: uuid.UUID, body: ClientUpdate, db: AsyncSession = Depends(get_db)
) -> Client:
    return await RegisterService(db).update_client(client_id, body)


# --- Projects -----------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectResponse], dependencies=EDITORS)
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[ProjectResponse]:
    return [_project(row) for row in await RegisterService(db).list_projects()]


@router.post(
    "/projects", status_code=201, response_model=ProjectResponse, dependencies=EDITORS
)
async def create_project(
    body: ProjectCreate, db: AsyncSession = Depends(get_db)
) -> ProjectResponse:
    service = RegisterService(db)
    project = await service.create_project(body)
    return _project(await service.project_row(project))


@router.patch(
    "/projects/{project_id}", response_model=ProjectResponse, dependencies=EDITORS
)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, db: AsyncSession = Depends(get_db)
) -> ProjectResponse:
    service = RegisterService(db)
    project = await service.update_project(project_id, body)
    return _project(await service.project_row(project))


# --- Placements ---------------------------------------------------------------


@router.get("/placements", response_model=list[PlacementResponse], dependencies=EDITORS)
async def list_placements(
    db: AsyncSession = Depends(get_db),
) -> list[PlacementResponse]:
    return [_placement(row) for row in await RegisterService(db).list_placements()]


@router.post(
    "/placements",
    status_code=201,
    response_model=PlacementResponse,
    dependencies=EDITORS,
)
async def create_placement(
    body: PlacementCreate, db: AsyncSession = Depends(get_db)
) -> PlacementResponse:
    service = RegisterService(db)
    placement = await service.create_placement(body)
    return _placement(await service.placement_row(placement.id))


@router.get("/placements/{placement_id}", response_model=PlacementResponse)
async def get_placement(
    placement: PlacementScope, db: AsyncSession = Depends(get_db)
) -> PlacementResponse:
    return _placement(await RegisterService(db).placement_row(placement.id))


@router.patch(
    "/placements/{placement_id}",
    response_model=PlacementResponse,
    dependencies=EDITORS,
)
async def update_placement(
    placement: PlacementScope,
    body: PlacementUpdate,
    db: AsyncSession = Depends(get_db),
) -> PlacementResponse:
    service = RegisterService(db)
    await service.update_placement(placement, body)
    return _placement(await service.placement_row(placement.id))


# --- CSV import ---------------------------------------------------------------


@router.post("/register/import", response_model=ImportResult, dependencies=EDITORS)
@limiter.limit("10/minute")
async def import_register(
    request: Request,
    file: UploadFile,
    dry_run: bool = Query(
        True, description="Preview only; set false to write (Confirm)"
    ),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import placements from a CSV. Always 200: ``applied`` says if it wrote.

    A dry run never writes. A Confirm writes every row, or none when any row
    has an error; the rows say why.
    """
    if not (file.filename or "").lower().endswith(".csv"):
        raise ValidationError("Upload a .csv file")
    content = await file.read(MAX_BYTES + 1)
    return await RegisterImport(db).run(content, dry_run=dry_run)


# --- Response mapping ---------------------------------------------------------


def _person(user: User | None) -> PersonRef | None:
    return PersonRef.model_validate(user) if user is not None else None


def _project(row: ProjectRow) -> ProjectResponse:
    project = row.project
    return ProjectResponse(
        id=project.id,
        client_id=row.client.id,
        client_name=row.client.name,
        name=project.name,
        client_manager_name=project.client_manager_name,
        tech_lead=_person(row.tech_lead),
        start_date=project.start_date,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _placement(row: PlacementRow) -> PlacementResponse:
    p = row.placement
    return PlacementResponse(
        id=p.id,
        consultant=PlacementConsultant(
            id=row.consultant.id,
            full_name=row.consultant.full_name,
            email=row.consultant.email,
        ),
        client=NamedRef(id=row.client.id, name=row.client.name),
        project=NamedRef(id=row.project.id, name=row.project.name),
        start_date=p.start_date,
        expected_end_date=p.expected_end_date,
        extension_status=ExtensionStatus(p.extension_status),
        rate_band=p.rate_band,
        status=PlacementStatus(p.status),
        ended_reason=p.ended_reason,
        ps=_person(row.ps),
        sme=_person(row.sme),
        tech_lead=_person(row.tech_lead),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )
