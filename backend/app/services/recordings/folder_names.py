"""Reading the PMO recordings folder: folder names and recording file names.

A folder is a recurring Nextcloud Talk room, named by hand. Surveyed
2026-10-08 (310 folders):

- 79 start with a ``DD-MM-YY`` date and 77 of those end in a routing suffix,
  ``#-#<ticket|ADHOC>#-#PMO#-#UK`` (three with ``#|#``); the suffix says
  nothing about the consultant and is dropped.
- 231 carry no date and no suffix, e.g. ``PRJ ITC BD - <name> - <client> -
  1-9-26 - 31-3-27``.
- 93 names hold an en dash (U+2013) as a separator. An earlier survey read
  these as U+FFFD through a cp1252 console; the keys themselves are clean.
- One folder has an empty name.

Recording files are mostly ``Recording YYYY-MM-DD HH-MM-SS.webm`` in the
call's local time; a few are ``V1_YYYY-MM-DDTHHMMSS.mp4`` (local time) or
``screen-recording-<epoch ms>.webm`` (an instant).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

_SUFFIX = re.compile(r"#[-|]#.*$", re.DOTALL)
_LEADING_DATE = re.compile(r"^\s*(\d{2})-(\d{2})-(\d{2})(?!\d)")
_NOT_WORD = re.compile(r"[^0-9a-z]+")

_TALK_RECORDING = re.compile(
    r"^Recording (\d{4})-(\d{2})-(\d{2}) (\d{2})-(\d{2})-(\d{2})\.\w+$"
)
_VERSIONED_RECORDING = re.compile(
    r"^V\d+_(\d{4})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})\.\w+$"
)
_SCREEN_RECORDING = re.compile(r"^screen-recording-(\d{13})\.\w+$")


@dataclass(frozen=True)
class FolderName:
    """A folder name read for display, dating and matching."""

    display_name: str
    folder_date: date | None
    # Folded words of the name without its date and suffix (see ``fold``).
    match_text: str


def fold(text: str) -> str:
    """Lower-case words without accents, separated by single spaces.

    ``"Zoë O'Brien – Acme"`` becomes ``"zoe o brien acme"``: every run of
    anything but a letter or digit (dashes of any kind, apostrophes, ``#``,
    underscores) is one separator, so a whole-word search is a substring
    search with spaces around it.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NOT_WORD.sub(" ", stripped.casefold()).strip()


def parse_folder_name(name: str) -> FolderName:
    display = _SUFFIX.sub("", name).strip()
    folder_date: date | None = None
    rest = display
    leading = _LEADING_DATE.match(display)
    if leading:
        day, month, year = (int(part) for part in leading.groups())
        try:
            folder_date = date(2000 + year, month, day)
        except ValueError:
            folder_date = None
        rest = display[leading.end() :]
    return FolderName(
        display_name=display, folder_date=folder_date, match_text=fold(rest)
    )


def recorded_at_from_filename(filename: str, timezone: str) -> datetime | None:
    """When the call in ``filename`` was recorded, in UTC; None if the name
    does not say. Local times are read in ``timezone``."""
    for pattern in (_TALK_RECORDING, _VERSIONED_RECORDING):
        found = pattern.match(filename)
        if found:
            year, month, day, hour, minute, second = (
                int(part) for part in found.groups()
            )
            try:
                local = datetime(
                    year, month, day, hour, minute, second, tzinfo=ZoneInfo(timezone)
                )
            except ValueError:
                return None
            return local.astimezone(UTC)
    screen = _SCREEN_RECORDING.match(filename)
    if screen:
        return datetime.fromtimestamp(int(screen.group(1)) / 1000, tz=UTC)
    return None
