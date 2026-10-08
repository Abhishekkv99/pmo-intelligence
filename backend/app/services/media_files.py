"""Checks every recording passes before it is stored: name, type and size.

Uploads and URL downloads share them. A recording is streamed in chunks, so
the size cap is enforced on the bytes actually received (a client's declared
size can lie) and the type is checked on the first bytes against the file's
extension, so a renamed file is refused with the reason.
"""

import re
from collections.abc import AsyncIterator
from pathlib import PurePosixPath

from app.utils.exceptions import ValidationError

# Enough leading bytes for every signature below.
SIGNATURE_BYTES = 12

_MATROSKA = b"\x1a\x45\xdf\xa3"
# ISO base media files (MP4, M4A) open with an "ftyp" box. Older QuickTime
# files may open with another top-level atom instead.
_ISO_BOX_TYPES = (b"ftyp",)
_QUICKTIME_BOX_TYPES = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")


def _is_mp3(head: bytes) -> bool:
    # An ID3 tag, or straight into an MPEG audio frame (11 sync bits set).
    return head.startswith(b"ID3") or (
        len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    )


def matches_extension(extension: str, head: bytes) -> bool:
    """Whether ``head`` (the file's first bytes) fits ``extension``."""
    match extension:
        case ".webm":
            return head.startswith(_MATROSKA)
        case ".mp4" | ".m4a":
            return head[4:8] in _ISO_BOX_TYPES
        case ".mov":
            return head[4:8] in _QUICKTIME_BOX_TYPES
        case ".mp3":
            return _is_mp3(head)
        case ".wav":
            return head.startswith(b"RIFF") and head[8:12] == b"WAVE"
        case ".ogg":
            return head.startswith(b"OggS")
        case _:
            return False


def extension_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def check_extension(filename: str, allowed: list[str]) -> str:
    """The file's lower-case extension, or a ValidationError naming the allowed ones."""
    extension = extension_of(filename)
    if extension not in allowed:
        shown = extension or "none"
        raise ValidationError(
            f"File type '{shown}' not allowed. Allowed: {', '.join(allowed)}"
        )
    return extension


def sanitize_filename(filename: str) -> str:
    """Keep letters, digits, ``-``, ``_`` and ``.``; no traversal; 200 chars at most."""
    sanitized = re.sub(r"[^\w\-.]", "_", PurePosixPath(filename).name)
    sanitized = sanitized.replace("..", "")
    if len(sanitized) > 200:
        extension = PurePosixPath(sanitized).suffix
        sanitized = sanitized[: 200 - len(extension)] + extension
    return sanitized or "recording"


async def checked_stream(
    chunks: AsyncIterator[bytes], *, extension: str, max_bytes: int
) -> AsyncIterator[bytes]:
    """Pass ``chunks`` through, refusing a wrong type or more than ``max_bytes``.

    The first bytes are held back until there are enough to check the
    signature (a network read may return only a few bytes), then released
    unchanged. Raises ValidationError mid-stream, which aborts the storage
    upload consuming it.
    """
    head = bytearray()
    checked = False
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise ValidationError(
                f"File too large. Maximum: {max_bytes // (1024 * 1024)}MB"
            )
        if checked:
            yield chunk
            continue
        head.extend(chunk)
        if len(head) < SIGNATURE_BYTES:
            continue
        _check_signature(extension, bytes(head))
        checked = True
        yield bytes(head)
        head.clear()
    if not checked:
        _check_signature(extension, bytes(head))
        if head:
            yield bytes(head)


def _check_signature(extension: str, head: bytes) -> None:
    if not head:
        raise ValidationError("The file is empty")
    if not matches_extension(extension, head):
        raise ValidationError(
            f"The file's content is not {extension[1:].upper()}; "
            "check that it is a recording and has the right extension"
        )
