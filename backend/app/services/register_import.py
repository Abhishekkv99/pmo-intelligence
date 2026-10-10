"""Seeding the placement register from a CSV, one row per placement.

The PS team keeps the register in a spreadsheet today; this imports it once
(BACKLOG #3) and can be re-run safely:

- a row creates what does not exist yet (client, consultant, project,
  placement) and updates what does: a filled cell overwrites the stored
  value, an empty cell leaves it as it is, so importing the same sheet twice
  changes nothing;
- people columns name existing users by email; the import never creates a
  user, because a user row is what lets someone sign in;
- the whole file is applied in one savepoint. A dry run always rolls it back,
  and so does a Confirm with any row error: either every row is written, or
  none is.

Rows are applied in file order, so a client or consultant created by one row
is found by the next, in a dry run as well.
"""

import csv
import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExtensionStatus, Role
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User
from app.schemas.register import ImportResult, ImportRowResult, ImportSummary
from app.services.register_service import RegisterService, normalize_name, tidy
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)

COLUMNS = (
    "consultant_full_name",
    "consultant_email",
    "client_name",
    "project_name",
    "client_manager_name",
    "tech_lead_email",
    "ps_email",
    "sme_email",
    "start_date",
    "expected_end_date",
    "extension_status",
    "rate_band",
)
REQUIRED = ("consultant_full_name", "client_name", "project_name", "start_date")
# The role each people column usually holds; a different role is a warning.
PEOPLE = {
    "tech_lead_email": Role.TECH_LEAD,
    "ps_email": Role.PS,
    "sme_email": Role.SME,
}
MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


@dataclass
class _Row:
    number: int
    values: dict[str, str]
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    created_placement: bool = False

    def get(self, column: str) -> str:
        return self.values.get(column, "")

    def result(self) -> ImportRowResult:
        if self.errors:
            outcome = "error"
        elif self.created_placement:
            outcome = "create"
        elif self.changes:
            outcome = "update"
        else:
            outcome = "unchanged"
        return ImportRowResult(
            row=self.number,
            outcome=outcome,
            consultant=self.get("consultant_full_name") or None,
            client=self.get("client_name") or None,
            project=self.get("project_name") or None,
            changes=self.changes,
            warnings=self.warnings,
            errors=self.errors,
        )


@dataclass(frozen=True)
class _Parsed:
    start_date: date
    end_date: date | None
    extension_status: ExtensionStatus | None
    people: dict[str, User]


class RegisterImport:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.register = RegisterService(session)
        # The placements an applied import created or changed (empty when it
        # wrote nothing), whose health the route then recomputes.
        self.changed_placement_ids: list[uuid.UUID] = []

    async def run(self, content: bytes, *, dry_run: bool) -> ImportResult:
        rows = read_rows(content)
        results: list[ImportRowResult] = []
        savepoint = await self.session.begin_nested()
        try:
            for row in rows:
                results.append(await self._apply_row(row))
        except BaseException:
            await savepoint.rollback()
            raise

        errors = sum(1 for r in results if r.outcome == "error")
        applied = not dry_run and errors == 0
        if applied:
            await savepoint.commit()
        else:
            await savepoint.rollback()
            self.changed_placement_ids = []
        logger.info(
            "Register import: rows=%d errors=%d dry_run=%s applied=%s",
            len(results),
            errors,
            dry_run,
            applied,
        )
        return ImportResult(
            dry_run=dry_run,
            applied=applied,
            summary=ImportSummary(
                rows=len(results),
                created=sum(1 for r in results if r.outcome == "create"),
                updated=sum(1 for r in results if r.outcome == "update"),
                unchanged=sum(1 for r in results if r.outcome == "unchanged"),
                errors=errors,
            ),
            rows=results,
        )

    async def _apply_row(self, row: _Row) -> ImportRowResult:
        parsed = await self._parse(row)
        if parsed is None:
            return row.result()
        # A row is all or nothing too: a failure part-way leaves no client or
        # consultant behind for a placement that was never written.
        row_savepoint = await self.session.begin_nested()
        try:
            await self._write(row, parsed)
        except ValidationError as exc:
            row.errors.append(exc.message)
        if row.errors:
            await row_savepoint.rollback()
            row.changes.clear()
            row.created_placement = False
        else:
            await row_savepoint.commit()
        return row.result()

    # --- Parsing and checks (no writes) -----------------------------------

    async def _parse(self, row: _Row) -> _Parsed | None:
        for column in REQUIRED:
            if not row.get(column):
                row.errors.append(f"{column} is required")

        start = _date(row, "start_date")
        end = _date(row, "expected_end_date")
        if start and end and end < start:
            row.errors.append("expected_end_date is before start_date")

        extension: ExtensionStatus | None = None
        if raw := row.get("extension_status"):
            try:
                extension = ExtensionStatus(raw.strip().lower().replace(" ", "_"))
            except ValueError:
                allowed = ", ".join(s.value for s in ExtensionStatus)
                row.errors.append(f"extension_status '{raw}' is not one of: {allowed}")

        email = row.get("consultant_email")
        if email and not _looks_like_email(email):
            row.errors.append(f"consultant_email '{email}' is not an email address")

        people: dict[str, User] = {}
        for column, usual_role in PEOPLE.items():
            address = row.get(column).lower()
            if not address:
                continue
            user = await self.register.users.get_by_email(address)
            if user is None or not user.is_active or user.role is None:
                row.errors.append(
                    f"{column} {address}: no active user with a role has this "
                    "email; grant them a role first"
                )
                continue
            if user.role != usual_role.value:
                row.warnings.append(
                    f"{column} {address} is a {user.role}, not a {usual_role.value}"
                )
            people[column] = user

        if row.errors or start is None:
            return None
        return _Parsed(start, end, extension, people)

    # --- Writes ------------------------------------------------------------

    async def _write(self, row: _Row, parsed: _Parsed) -> None:
        client = await self._client(row)
        consultant = await self._consultant(row)
        if consultant is None:
            return
        project = await self._project(row, client, parsed)
        await self._placement(row, consultant, project, parsed)
        await self.session.flush()

    async def _client(self, row: _Row) -> Client:
        name = tidy(row.get("client_name"))
        client = await self.register.clients.get_by_normalized_name(
            normalize_name(name)
        )
        if client is not None:
            return client
        row.changes.append(f"client {name}: created")
        return await self.register.clients.create(
            name=name, normalized_name=normalize_name(name)
        )

    async def _consultant(self, row: _Row) -> Consultant | None:
        name = tidy(row.get("consultant_full_name"))
        email = row.get("consultant_email").lower() or None
        repo = self.register.consultants

        consultant = await repo.get_by_email(email) if email else None
        if consultant is None:
            same_name = await repo.list_by_full_name(name)
            if email:
                # Someone entered by name only earlier gains the email now.
                same_name = [c for c in same_name if c.email is None]
            if len(same_name) > 1:
                row.errors.append(
                    f"several consultants are named {name}; "
                    "add consultant_email to say which"
                )
                return None
            consultant = same_name[0] if same_name else None

        if consultant is None:
            row.changes.append(f"consultant {name}: created")
            return await repo.create(full_name=name, email=email)

        if consultant.full_name != name:
            row.changes.append(f"consultant name: {consultant.full_name} -> {name}")
            consultant.full_name = name
        if email and consultant.email != email:
            row.changes.append(f"consultant {name} email: {email}")
            consultant.email = email
        return consultant

    async def _project(self, row: _Row, client: Client, parsed: _Parsed) -> Project:
        name = tidy(row.get("project_name"))
        manager = tidy(row.get("client_manager_name")) or None
        lead = parsed.people.get("tech_lead_email")
        repo = self.register.projects

        project = await repo.get_by_client_and_name(client.id, name)
        if project is None:
            row.changes.append(f"project {client.name} / {name}: created")
            return await repo.create(
                client_id=client.id,
                name=name,
                client_manager_name=manager,
                tech_lead_user_id=lead.id if lead else None,
            )
        if manager and project.client_manager_name != manager:
            row.changes.append(
                f"project client manager: {project.client_manager_name or '-'} "
                f"-> {manager}"
            )
            project.client_manager_name = manager
        if lead and project.tech_lead_user_id != lead.id:
            row.changes.append(f"project tech lead: {lead.email}")
            project.tech_lead_user_id = lead.id
        return project

    async def _placement(
        self,
        row: _Row,
        consultant: Consultant,
        project: Project,
        parsed: _Parsed,
    ) -> Placement:
        repo = self.register.placements
        ps = parsed.people.get("ps_email")
        sme = parsed.people.get("sme_email")
        rate_band = row.get("rate_band") or None

        placement = await repo.get_by_key(consultant.id, project.id, parsed.start_date)
        if placement is None:
            row.created_placement = True
            row.changes.append(f"placement from {parsed.start_date}: created")
            created = await repo.create(
                consultant_id=consultant.id,
                project_id=project.id,
                start_date=parsed.start_date,
                expected_end_date=parsed.end_date,
                extension_status=(
                    parsed.extension_status or ExtensionStatus.NOT_DUE
                ).value,
                rate_band=rate_band,
                ps_user_id=ps.id if ps else None,
                sme_user_id=sme.id if sme else None,
            )
            self._changed(created.id)
            return created

        updates: dict[str, object] = {}
        if parsed.end_date and placement.expected_end_date != parsed.end_date:
            updates["expected_end_date"] = parsed.end_date
        if (
            parsed.extension_status
            and placement.extension_status != parsed.extension_status.value
        ):
            updates["extension_status"] = parsed.extension_status.value
        if rate_band and placement.rate_band != rate_band:
            updates["rate_band"] = rate_band
        if ps and placement.ps_user_id != ps.id:
            updates["ps_user_id"] = ps.id
        if sme and placement.sme_user_id != sme.id:
            updates["sme_user_id"] = sme.id
        for key, value in updates.items():
            if key == "ps_user_id" and ps:
                row.changes.append(f"placement PS: {ps.email}")
            elif key == "sme_user_id" and sme:
                row.changes.append(f"placement SME: {sme.email}")
            else:
                old = getattr(placement, key) or "-"
                row.changes.append(f"placement {key}: {old} -> {value}")
            setattr(placement, key, value)
        if updates:
            self._changed(placement.id)
        return placement

    def _changed(self, placement_id: uuid.UUID) -> None:
        if placement_id not in self.changed_placement_ids:
            self.changed_placement_ids.append(placement_id)


def read_rows(content: bytes) -> list[_Row]:
    """Decode and split the file; problems with the file itself raise 422."""
    if len(content) > MAX_BYTES:
        raise ValidationError("The file is larger than 1 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'"
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    header = [(name or "").strip().lower() for name in reader.fieldnames or []]
    if not header:
        raise ValidationError("The file is empty")
    missing = [c for c in COLUMNS if c not in header]
    unknown = [c for c in header if c and c not in COLUMNS]
    if missing or unknown:
        parts = []
        if missing:
            parts.append("missing columns: " + ", ".join(missing))
        if unknown:
            parts.append("unknown columns: " + ", ".join(unknown))
        raise ValidationError("; ".join(parts))
    reader.fieldnames = header

    rows: list[_Row] = []
    for raw in reader:
        values = {k: (v or "").strip() for k, v in raw.items() if k in COLUMNS}
        if not any(values.values()):
            continue
        if len(rows) == MAX_ROWS:
            raise ValidationError(f"The file has more than {MAX_ROWS} rows")
        # line_num counts physical lines read, so it matches the file's line
        rows.append(_Row(number=reader.line_num, values=values))
    if not rows:
        raise ValidationError("The file has a header but no rows")
    return rows


def _date(row: _Row, column: str) -> date | None:
    raw = row.get(column)
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    row.errors.append(f"{column} '{raw}' is not a date (YYYY-MM-DD or DD/MM/YYYY)")
    return None


def _looks_like_email(value: str) -> bool:
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and " " not in value
