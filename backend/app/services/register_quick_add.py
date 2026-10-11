"""Quick add: placements entered as lines in the Teams chat name format.

Each consultant's Teams group chat (and their recordings folder) is named

    PRJ ITC <stack> - <consultant> - <client> - <start> - <end>

e.g. ``PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027``.
One such line is enough to put a placement in the register:

- the separator is a hyphen or an en dash with spaces around it (names copied
  from Teams and from the folders use both); dates are ``D/M/YYYY`` or
  ``D-M-YY`` (the folders' form); anything else is an error on that line;
- the client is found by its normalised name, or created;
- the consultant is found by full name, or created (status ``placed``, no
  email); two consultants with that name are an error on the line;
- the placement is found by consultant, client and start date, on any of the
  client's projects, so renaming the project later keeps it; it is then
  updated (end date, stack) or left unchanged;
- a new placement goes under the client's project "To be confirmed" (created
  when missing): the real project name is the Teams chat's, which the app
  cannot read yet, and is entered on the Projects tab meanwhile.

The lines are applied in one savepoint. A dry run always rolls it back, and
so does a Confirm with any line error: either every line is written, or none
is. Lines apply in order, so a client or consultant created by one line is
found by the next, in a dry run as well.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.register import Client, Consultant, Placement
from app.schemas.register import QuickAddLineResult, QuickAddResult, QuickAddSummary
from app.services.register_service import RegisterService, normalize_name, tidy
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)

PROJECT_TO_BE_CONFIRMED = "To be confirmed"
FORMAT = "PRJ ITC <stack> - <consultant> - <client> - <start> - <end>"
MAX_NAME = 255
MAX_STACK = 50

_SEPARATOR = re.compile(r"\s+[-–]\s+")
_PREFIX = re.compile(r"^PRJ\s+ITC\s+(\S.*)$", re.IGNORECASE)
_SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DASH_DATE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2})$")


class LineFormatError(ValueError):
    """A line that does not follow the chat name format; the message says why."""


@dataclass(frozen=True)
class ParsedLine:
    stack: str
    consultant: str
    client: str
    start_date: date
    end_date: date


def parse_line(text: str) -> ParsedLine:
    """Read one line; raises ``LineFormatError`` with a reason."""
    parts = _SEPARATOR.split(text.strip())
    if len(parts) != 5:
        raise LineFormatError(
            f"expected 5 parts separated by ' - ', found {len(parts)}: {FORMAT}"
        )
    prefix, consultant, client, start, end = (tidy(part) for part in parts)
    head = _PREFIX.match(prefix)
    if head is None:
        raise LineFormatError(f"'{prefix}' should read 'PRJ ITC <stack>': {FORMAT}")
    stack = tidy(head.group(1))
    if len(stack) > MAX_STACK:
        raise LineFormatError(f"the stack is longer than {MAX_STACK} characters")
    for label, value in (("consultant", consultant), ("client", client)):
        if not value:
            raise LineFormatError(f"the {label} name is empty")
        if len(value) > MAX_NAME:
            raise LineFormatError(
                f"the {label} name is longer than {MAX_NAME} characters"
            )
    start_date = _date(start, "start")
    end_date = _date(end, "end")
    if end_date < start_date:
        raise LineFormatError("the end date is before the start date")
    return ParsedLine(stack, consultant, client, start_date, end_date)


def _date(raw: str, label: str) -> date:
    slash = _SLASH_DATE.match(raw)
    dash = _DASH_DATE.match(raw)
    if slash:
        day, month, year = (int(part) for part in slash.groups())
    elif dash:
        day, month, short_year = (int(part) for part in dash.groups())
        year = 2000 + short_year
    else:
        raise LineFormatError(f"the {label} date '{raw}' is not D/M/YYYY or D-M-YY")
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise LineFormatError(f"the {label} date '{raw}' is not a real date") from exc


@dataclass
class _Line:
    number: int
    text: str
    parsed: ParsedLine | None = None
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    created_placement: bool = False

    def result(self) -> QuickAddLineResult:
        if self.errors:
            outcome = "error"
        elif self.created_placement:
            outcome = "create"
        elif self.changes:
            outcome = "update"
        else:
            outcome = "unchanged"
        p = self.parsed
        return QuickAddLineResult(
            line=self.number,
            text=self.text,
            outcome=outcome,
            stack=p.stack if p else None,
            consultant=p.consultant if p else None,
            client=p.client if p else None,
            start_date=p.start_date if p else None,
            expected_end_date=p.end_date if p else None,
            changes=self.changes,
            errors=self.errors,
        )


class QuickAdd:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.register = RegisterService(session)
        # The placements an applied quick add created or changed (empty when
        # it wrote nothing), whose health the route then recomputes.
        self.changed_placement_ids: list[uuid.UUID] = []

    async def run(self, lines: list[str], *, dry_run: bool) -> QuickAddResult:
        numbered = [
            _Line(number, text.strip())
            for number, text in enumerate(lines, start=1)
            if text.strip()
        ]
        if not numbered:
            raise ValidationError("Paste at least one line")

        savepoint = await self.session.begin_nested()
        try:
            results = [await self._apply(line) for line in numbered]
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
            "Register quick add: lines=%d errors=%d dry_run=%s applied=%s",
            len(results),
            errors,
            dry_run,
            applied,
        )
        return QuickAddResult(
            dry_run=dry_run,
            applied=applied,
            summary=QuickAddSummary(
                lines=len(results),
                created=sum(1 for r in results if r.outcome == "create"),
                updated=sum(1 for r in results if r.outcome == "update"),
                unchanged=sum(1 for r in results if r.outcome == "unchanged"),
                errors=errors,
            ),
            lines=results,
        )

    async def _apply(self, line: _Line) -> QuickAddLineResult:
        try:
            line.parsed = parse_line(line.text)
        except LineFormatError as exc:
            line.errors.append(str(exc))
            return line.result()
        # A line is all or nothing too: a failure part-way leaves no client or
        # consultant behind for a placement that was never written.
        line_savepoint = await self.session.begin_nested()
        try:
            await self._write(line, line.parsed)
        except ValidationError as exc:
            line.errors.append(exc.message)
        if line.errors:
            await line_savepoint.rollback()
            line.changes.clear()
            line.created_placement = False
        else:
            await line_savepoint.commit()
        return line.result()

    async def _write(self, line: _Line, parsed: ParsedLine) -> None:
        client = await self._client(line, parsed.client)
        consultant = await self._consultant(line, parsed.consultant)
        if consultant is None:
            return
        await self._placement(line, parsed, consultant, client)
        await self.session.flush()

    async def _client(self, line: _Line, name: str) -> Client:
        repo = self.register.clients
        client = await repo.get_by_normalized_name(normalize_name(name))
        if client is not None:
            return client
        line.changes.append(f"client {name}: created")
        return await repo.create(name=name, normalized_name=normalize_name(name))

    async def _consultant(self, line: _Line, name: str) -> Consultant | None:
        repo = self.register.consultants
        same_name = await repo.list_by_full_name(name)
        if len(same_name) > 1:
            line.errors.append(
                f"several consultants are named {name}; "
                "add this placement on the Placements tab instead"
            )
            return None
        if same_name:
            return same_name[0]
        line.changes.append(f"consultant {name}: created")
        return await repo.create(full_name=name)

    async def _placement(
        self,
        line: _Line,
        parsed: ParsedLine,
        consultant: Consultant,
        client: Client,
    ) -> Placement | None:
        repo = self.register.placements
        existing = await repo.list_for_consultant_client_start(
            consultant.id, client.id, parsed.start_date
        )
        if len(existing) > 1:
            line.errors.append(
                f"{consultant.full_name} has {len(existing)} placements at "
                f"{client.name} from {parsed.start_date}; edit the right one on "
                "the Placements tab"
            )
            return None

        if existing:
            placement = existing[0]
            if placement.expected_end_date != parsed.end_date:
                old = placement.expected_end_date or "-"
                line.changes.append(f"end date: {old} -> {parsed.end_date}")
                placement.expected_end_date = parsed.end_date
            if placement.stack != parsed.stack:
                line.changes.append(
                    f"stack: {placement.stack or '-'} -> {parsed.stack}"
                )
                placement.stack = parsed.stack
            if line.changes:
                self._changed(placement.id)
            return placement

        projects = self.register.projects
        project = await projects.get_by_client_and_name(
            client.id, PROJECT_TO_BE_CONFIRMED
        )
        if project is None:
            line.changes.append(
                f"project {client.name} / {PROJECT_TO_BE_CONFIRMED}: created"
            )
            project = await projects.create(
                client_id=client.id, name=PROJECT_TO_BE_CONFIRMED
            )
        line.created_placement = True
        line.changes.append(
            f"placement {parsed.start_date} to {parsed.end_date}: created"
        )
        created = await repo.create(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=parsed.start_date,
            expected_end_date=parsed.end_date,
            stack=parsed.stack,
        )
        self._changed(created.id)
        return created

    def _changed(self, placement_id: uuid.UUID) -> None:
        if placement_id not in self.changed_placement_ids:
            self.changed_placement_ids.append(placement_id)
