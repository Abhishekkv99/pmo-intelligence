"""Reading a PMO group chat's title: ``PRJ ITC <stack> - <consultant> - <client> -
<start> - <end>``.

The titles are typed by hand. Surveyed 2026-10-14 (151 ``PRJ ITC`` chats), only
42 follow the quick add's strict line format; the others vary in ways this
parser accepts:

- separators: a hyphen or an en dash, with or without spaces around it (a bare
  hyphen splits the name part only when the spaced separators do not give
  three parts, so ``Jean-Paul`` or ``Coca-Cola`` survive in a spaced title);
- the prefix: ``PRJ ITC DS``, ``PRJ ITC-DS`` or ``PRJ ITC - DS``, in any case;
- dates: ``D/M/YYYY``, ``D/M/YY``, ``D-M-YY``, ``D-M-YYYY`` or ``YYYY-MM-DD``,
  in brackets or not; a two-digit year is 20YY.

A title that still cannot be read (a missing or extra part, no two dates at
the end, an impossible date, an end before the start) raises
``TitleFormatError`` with the reason, and the chat waits for a person on
Admin > Teams. The quick add's own ``parse_line`` stays strict.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.services.register_service import tidy

FORMAT = "PRJ ITC <stack> - <consultant> - <client> - <start> - <end>"

_PREFIX = re.compile(r"^\s*PRJ\s*ITC(?![A-Za-z0-9])\s*[-–]?\s*", re.IGNORECASE)
_DATE = re.compile(
    r"(?<!\d)(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2}))(?!\d)"
)
# What may sit between and after the two dates: separators, brackets, spaces.
_DATE_GAP = re.compile(r"^[\s\-–()\[\]]*$")
_TRAILING_SEPARATORS = re.compile(r"[\s\-–(\[]+$")
_SPACED_SEPARATOR = re.compile(r"\s*–\s*|\s+-\s+")
_ANY_SEPARATOR = re.compile(r"\s*[-–]\s*")


class TitleFormatError(ValueError):
    """A title this parser cannot read; the message says why."""


@dataclass(frozen=True)
class ChatTitle:
    stack: str
    consultant: str
    client: str
    start_date: date
    end_date: date


def is_pmo_title(title: str | None) -> bool:
    """Whether a chat title marks a PMO group chat (``PRJ ITC`` at the start)."""
    return bool(title) and _PREFIX.match(title or "") is not None


def parse_chat_title(title: str) -> ChatTitle:
    """Read a chat title; raises ``TitleFormatError`` with a reason."""
    prefix = _PREFIX.match(title)
    if prefix is None:
        raise TitleFormatError(f"the title does not start with 'PRJ ITC': {FORMAT}")
    rest = title[prefix.end() :]

    dates = list(_DATE.finditer(rest))
    if len(dates) < 2:
        raise TitleFormatError(
            f"expected a start and an end date at the end, found {len(dates)}"
        )
    first, second = dates[-2], dates[-1]
    if not _DATE_GAP.match(rest[first.end() : second.start()]) or not _DATE_GAP.match(
        rest[second.end() :]
    ):
        raise TitleFormatError("the start and end dates must end the title")
    start_date = _date(first, "start")
    end_date = _date(second, "end")
    if end_date < start_date:
        raise TitleFormatError("the end date is before the start date")

    head = _TRAILING_SEPARATORS.sub("", rest[: first.start()])
    parts = [tidy(part) for part in _SPACED_SEPARATOR.split(head)]
    if len(parts) != 3:
        parts = [tidy(part) for part in _ANY_SEPARATOR.split(head)]
    parts = [part for part in parts if part]
    if len(parts) != 3:
        raise TitleFormatError(
            "expected the stack, the consultant and the client before the dates, "
            f"found {len(parts)} part(s): {FORMAT}"
        )
    stack, consultant, client = parts
    return ChatTitle(stack, consultant, client, start_date, end_date)


def _date(found: re.Match[str], label: str) -> date:
    iso_year, iso_month, iso_day, day, month, year = found.groups()
    try:
        if iso_year is not None:
            return date(int(iso_year), int(iso_month), int(iso_day))
        full_year = int(year) + 2000 if len(year) == 2 else int(year)
        return date(full_year, int(month), int(day))
    except ValueError as exc:
        raise TitleFormatError(
            f"the {label} date '{found.group(0)}' is not a real date"
        ) from exc
