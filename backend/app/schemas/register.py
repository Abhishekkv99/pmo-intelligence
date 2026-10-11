"""Request and response models for the placement register.

Updates are partial (``PATCH``): only the fields sent are applied, and an
explicit ``null`` clears a nullable field. Services read the sent fields with
``model_dump(exclude_unset=True)``.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import ConsultantStatus, ExtensionStatus, PlacementStatus

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Skill = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class PersonRef(BaseModel):
    """A user named on a placement (PS, SME) or a consultant (CDM)."""

    id: uuid.UUID
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


# --- Consultants --------------------------------------------------------------


class ConsultantCreate(BaseModel):
    full_name: Name
    email: EmailStr | None = None
    phone: ShortText | None = None
    skills: list[Skill] = Field(default_factory=list, max_length=50)
    status: ConsultantStatus = ConsultantStatus.PLACED
    cdm_user_id: uuid.UUID | None = None


class ConsultantUpdate(BaseModel):
    full_name: Name | None = None
    email: EmailStr | None = None
    phone: ShortText | None = None
    skills: list[Skill] | None = Field(default=None, max_length=50)
    status: ConsultantStatus | None = None
    cdm_user_id: uuid.UUID | None = None


class ConsultantResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    skills: list[str]
    status: ConsultantStatus
    # The Consultant Director who manages the consultant.
    cdm: PersonRef | None
    created_at: datetime
    updated_at: datetime


# --- Clients ------------------------------------------------------------------


class ClientCreate(BaseModel):
    name: Name
    industry: OptionalText | None = None


class ClientUpdate(BaseModel):
    name: Name | None = None
    industry: OptionalText | None = None


class ClientResponse(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Projects -----------------------------------------------------------------


class ProjectCreate(BaseModel):
    client_id: uuid.UUID
    name: Name
    client_manager_name: OptionalText | None = None
    start_date: date | None = None


class ProjectUpdate(BaseModel):
    client_id: uuid.UUID | None = None
    name: Name | None = None
    client_manager_name: OptionalText | None = None
    start_date: date | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    name: str
    client_manager_name: str | None
    start_date: date | None
    created_at: datetime
    updated_at: datetime


# --- Placements ---------------------------------------------------------------


class PlacementCreate(BaseModel):
    consultant_id: uuid.UUID
    project_id: uuid.UUID
    start_date: date
    expected_end_date: date | None = None
    extension_status: ExtensionStatus = ExtensionStatus.NOT_DUE
    rate_band: ShortText | None = None
    stack: ShortText | None = None
    ps_user_id: uuid.UUID | None = None
    sme_user_id: uuid.UUID | None = None
    status: PlacementStatus = PlacementStatus.ACTIVE
    ended_reason: LongText | None = None


class PlacementUpdate(BaseModel):
    consultant_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    start_date: date | None = None
    expected_end_date: date | None = None
    extension_status: ExtensionStatus | None = None
    rate_band: ShortText | None = None
    stack: ShortText | None = None
    ps_user_id: uuid.UUID | None = None
    sme_user_id: uuid.UUID | None = None
    status: PlacementStatus | None = None
    ended_reason: LongText | None = None


class PlacementConsultant(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class PlacementResponse(BaseModel):
    id: uuid.UUID
    consultant: PlacementConsultant
    client: NamedRef
    project: NamedRef
    start_date: date
    expected_end_date: date | None
    # Null for an SME, with rate_band and ended_reason: contract matters.
    extension_status: ExtensionStatus | None
    rate_band: str | None
    stack: str | None
    status: PlacementStatus
    ended_reason: str | None
    ps: PersonRef | None
    sme: PersonRef | None
    # The consultant's CDM.
    cdm: PersonRef | None
    created_at: datetime
    updated_at: datetime


# --- Quick add ----------------------------------------------------------------

QuickAddLine = Annotated[str, StringConstraints(max_length=500)]


class QuickAddRequest(BaseModel):
    """Lines in the Teams chat name format; blank lines are skipped."""

    lines: list[QuickAddLine] = Field(min_length=1, max_length=200)


class QuickAddLineResult(BaseModel):
    """What one line did, or would do on Confirm."""

    line: int = Field(description="Position among the lines sent, from 1")
    text: str
    outcome: str = Field(description="create, update, unchanged or error")
    stack: str | None
    consultant: str | None
    client: str | None
    start_date: date | None
    expected_end_date: date | None
    changes: list[str]
    errors: list[str]


class QuickAddSummary(BaseModel):
    lines: int
    created: int
    updated: int
    unchanged: int
    errors: int


class QuickAddResult(BaseModel):
    dry_run: bool
    # True only when this call wrote the lines: a Confirm with no line errors.
    applied: bool
    summary: QuickAddSummary
    lines: list[QuickAddLineResult]
