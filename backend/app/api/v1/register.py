"""The placement register: consultants, clients, projects, placements, quick add.

Editing the register is for the global roles (PMO manager, admin). Reading a
single placement by id is scoped like every by-id read: the people it names
may read it, anyone else gets the same 404 as for a missing placement. An SME
reads it without the contract fields (extension status, rate band, ended
reason), as on the placement health page.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.db.repositories.placement_repo import PlacementRow
from app.dependencies import (
    DbSession,
    PlacementScope,
    get_current_user,
    require_roles,
)
from app.models.enums import (
    ConsultantStatus,
    ExtensionStatus,
    PlacementStatus,
    Role,
    SnapshotReason,
)
from app.models.register import Client
from app.models.user import User
from app.rate_limiter import limiter
from app.schemas.register import (
    ClientCreate,
    ClientResponse,
    ClientUpdate,
    ConsultantCreate,
    ConsultantResponse,
    ConsultantUpdate,
    NamedRef,
    PersonRef,
    PlacementConsultant,
    PlacementCreate,
    PlacementResponse,
    PlacementUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    QuickAddRequest,
    QuickAddResult,
)
from app.services.health_jobs import request_recompute, request_recomputes
from app.services.register_quick_add import QuickAdd
from app.services.register_service import ConsultantRow, ProjectRow, RegisterService
from app.services.teams.jobs import request_placement_watch
from app.utils.entitlements import sees_technical_only

router = APIRouter()

EDITORS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


# --- Consultants --------------------------------------------------------------


@router.get(
    "/consultants", response_model=list[ConsultantResponse], dependencies=EDITORS
)
async def list_consultants(db: DbSession) -> list[ConsultantResponse]:
    return [_consultant(row) for row in await RegisterService(db).list_consultants()]


@router.post(
    "/consultants",
    status_code=201,
    response_model=ConsultantResponse,
    dependencies=EDITORS,
)
async def create_consultant(
    body: ConsultantCreate, db: DbSession
) -> ConsultantResponse:
    service = RegisterService(db)
    consultant = await service.create_consultant(body)
    return _consultant(await service.consultant_row(consultant))


@router.patch(
    "/consultants/{consultant_id}",
    response_model=ConsultantResponse,
    dependencies=EDITORS,
)
async def update_consultant(
    consultant_id: uuid.UUID,
    body: ConsultantUpdate,
    db: DbSession,
) -> ConsultantResponse:
    service = RegisterService(db)
    consultant = await service.update_consultant(consultant_id, body)
    return _consultant(await service.consultant_row(consultant))


# --- Clients ------------------------------------------------------------------


@router.get("/clients", response_model=list[ClientResponse], dependencies=EDITORS)
async def list_clients(db: DbSession) -> list[Client]:
    return await RegisterService(db).list_clients()


@router.post(
    "/clients", status_code=201, response_model=ClientResponse, dependencies=EDITORS
)
async def create_client(body: ClientCreate, db: DbSession) -> Client:
    return await RegisterService(db).create_client(body)


@router.patch(
    "/clients/{client_id}", response_model=ClientResponse, dependencies=EDITORS
)
async def update_client(
    client_id: uuid.UUID, body: ClientUpdate, db: DbSession
) -> Client:
    return await RegisterService(db).update_client(client_id, body)


# --- Projects -----------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectResponse], dependencies=EDITORS)
async def list_projects(db: DbSession) -> list[ProjectResponse]:
    return [_project(row) for row in await RegisterService(db).list_projects()]


@router.post(
    "/projects", status_code=201, response_model=ProjectResponse, dependencies=EDITORS
)
async def create_project(body: ProjectCreate, db: DbSession) -> ProjectResponse:
    service = RegisterService(db)
    project = await service.create_project(body)
    return _project(await service.project_row(project))


@router.patch(
    "/projects/{project_id}", response_model=ProjectResponse, dependencies=EDITORS
)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, db: DbSession
) -> ProjectResponse:
    service = RegisterService(db)
    project = await service.update_project(project_id, body)
    row = await service.project_row(project)
    placement_ids = await service.active_placement_ids(project.id)
    await db.commit()
    request_recomputes(placement_ids, SnapshotReason.REGISTER)
    return _project(row)


# --- Placements ---------------------------------------------------------------


@router.get("/placements", response_model=list[PlacementResponse], dependencies=EDITORS)
async def list_placements(
    db: DbSession,
) -> list[PlacementResponse]:
    return [_placement(row) for row in await RegisterService(db).list_placements()]


@router.post(
    "/placements",
    status_code=201,
    response_model=PlacementResponse,
    dependencies=EDITORS,
)
async def create_placement(body: PlacementCreate, db: DbSession) -> PlacementResponse:
    service = RegisterService(db)
    placement = await service.create_placement(body)
    row = await service.placement_row(placement.id)
    await db.commit()
    request_recompute(placement.id, SnapshotReason.REGISTER)
    request_placement_watch([placement.id])
    return _placement(row)


@router.get("/placements/{placement_id}", response_model=PlacementResponse)
async def get_placement(
    placement: PlacementScope,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> PlacementResponse:
    row = await RegisterService(db).placement_row(placement.id)
    return _placement(row, contract=not sees_technical_only(current_user))


@router.patch(
    "/placements/{placement_id}",
    response_model=PlacementResponse,
    dependencies=EDITORS,
)
async def update_placement(
    placement: PlacementScope,
    body: PlacementUpdate,
    db: DbSession,
) -> PlacementResponse:
    service = RegisterService(db)
    await service.update_placement(placement, body)
    row = await service.placement_row(placement.id)
    await db.commit()
    request_recompute(placement.id, SnapshotReason.REGISTER)
    request_placement_watch([placement.id])
    return _placement(row)


# --- Quick add ----------------------------------------------------------------


@router.post("/register/quick-add", response_model=QuickAddResult, dependencies=EDITORS)
@limiter.limit("10/minute")
async def quick_add(
    request: Request,
    body: QuickAddRequest,
    db: DbSession,
    dry_run: bool = Query(
        True, description="Preview only; set false to write (Confirm)"
    ),
) -> QuickAddResult:
    """Add placements from lines in the Teams chat name format. Always 200:
    ``applied`` says if it wrote.

    A dry run never writes. A Confirm writes every line, or none when any line
    has an error; the lines say why.
    """
    adder = QuickAdd(db)
    result = await adder.run(body.lines, dry_run=dry_run)
    if result.applied:
        await db.commit()
        request_recomputes(adder.changed_placement_ids, SnapshotReason.REGISTER)
        request_placement_watch(adder.changed_placement_ids)
    return result


# --- Response mapping ---------------------------------------------------------


def _person(user: User | None) -> PersonRef | None:
    return PersonRef.model_validate(user) if user is not None else None


def _consultant(row: ConsultantRow) -> ConsultantResponse:
    c = row.consultant
    return ConsultantResponse(
        id=c.id,
        full_name=c.full_name,
        email=c.email,
        phone=c.phone,
        skills=c.skills,
        status=ConsultantStatus(c.status),
        cdm=_person(row.cdm),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _project(row: ProjectRow) -> ProjectResponse:
    project = row.project
    return ProjectResponse(
        id=project.id,
        client_id=row.client.id,
        client_name=row.client.name,
        name=project.name,
        client_manager_name=project.client_manager_name,
        start_date=project.start_date,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _placement(row: PlacementRow, *, contract: bool = True) -> PlacementResponse:
    """``contract`` False leaves out the contract fields (an SME's read)."""
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
        extension_status=ExtensionStatus(p.extension_status) if contract else None,
        rate_band=p.rate_band if contract else None,
        stack=p.stack,
        status=PlacementStatus(p.status),
        ended_reason=p.ended_reason if contract else None,
        ps=_person(row.ps),
        sme=_person(row.sme),
        cdm=_person(row.cdm),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )
