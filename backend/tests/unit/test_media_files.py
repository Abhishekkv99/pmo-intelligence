"""Recording checks shared by uploads and URL downloads: type, size, name."""

from collections.abc import AsyncIterator

import pytest

from app.services.media_files import (
    check_extension,
    checked_stream,
    matches_extension,
    playback_type,
    sanitize_filename,
)
from app.utils.exceptions import ValidationError

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 52
MOV_OLD = b"\x00\x00\x00\x08wide" + b"\x00" * 56
MP3_ID3 = b"ID3\x04\x00" + b"\x00" * 59
MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 60
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 48
OGG = b"OggS\x00\x02" + b"\x00" * 58

ALLOWED = [".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".ogg"]


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _drain(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in stream])


class TestMatchesExtension:
    @pytest.mark.parametrize(
        ("extension", "head"),
        [
            (".webm", WEBM),
            (".mp4", MP4),
            (".m4a", MP4),
            (".mov", MP4),
            (".mov", MOV_OLD),
            (".mp3", MP3_ID3),
            (".mp3", MP3_FRAME),
            (".wav", WAV),
            (".ogg", OGG),
        ],
    )
    def test_signature_for_its_extension_matches(
        self, extension: str, head: bytes
    ) -> None:
        assert matches_extension(extension, head)

    @pytest.mark.parametrize(
        ("extension", "head"),
        [
            (".webm", MP4),
            (".mp4", WEBM),
            (".mp4", MOV_OLD),
            (".mp3", WAV),
            (".wav", OGG),
            (".ogg", b"<html><body>Sign in</body></html>"),
            (".exe", b"MZ" + b"\x00" * 30),
        ],
    )
    def test_signature_of_another_type_does_not_match(
        self, extension: str, head: bytes
    ) -> None:
        assert not matches_extension(extension, head)


class TestCheckExtension:
    def test_allowed_extension_is_returned_lower_case(self) -> None:
        assert check_extension("Recording 2026-10-01.WEBM", ALLOWED) == ".webm"

    @pytest.mark.parametrize("name", ["notes.pdf", "recording", "clip.webm.exe"])
    def test_other_extension_is_refused_with_the_allowed_list(self, name: str) -> None:
        with pytest.raises(ValidationError, match="Allowed: .mp4"):
            check_extension(name, ALLOWED)


class TestSanitizeFilename:
    def test_spaces_and_symbols_become_underscores(self) -> None:
        assert (
            sanitize_filename("Recording 2026-10-01 10-00-00.webm")
            == "Recording_2026-10-01_10-00-00.webm"
        )

    def test_path_parts_and_traversal_are_dropped(self) -> None:
        assert sanitize_filename("../../etc/passwd.webm") == "passwd.webm"
        assert ".." not in sanitize_filename("evil..webm")

    def test_long_name_keeps_its_extension(self) -> None:
        name = sanitize_filename("a" * 300 + ".webm")
        assert len(name) == 200
        assert name.endswith(".webm")

    def test_name_with_nothing_left_gets_a_default(self) -> None:
        assert sanitize_filename("..") == "recording"


class TestCheckedStream:
    async def test_matching_file_passes_through_unchanged(self) -> None:
        body = WEBM + b"rest of the file"
        stream = checked_stream(
            _chunks(body[:5], body[5:20], body[20:]), extension=".webm", max_bytes=1000
        )
        assert await _drain(stream) == body

    async def test_signature_split_over_tiny_chunks_is_still_checked(self) -> None:
        chunks = [MP4[i : i + 1] for i in range(len(MP4))]
        stream = checked_stream(_chunks(*chunks), extension=".mp4", max_bytes=1000)
        assert await _drain(stream) == MP4

    async def test_file_shorter_than_the_signature_window_is_checked_at_the_end(
        self,
    ) -> None:
        stream = checked_stream(_chunks(b"OggS"), extension=".ogg", max_bytes=1000)
        assert await _drain(stream) == b"OggS"

    async def test_wrong_content_is_refused_before_any_byte_is_released(
        self,
    ) -> None:
        released: list[bytes] = []
        stream = checked_stream(
            _chunks(b"<html>", b"<body>not a recording</body>"),
            extension=".webm",
            max_bytes=1000,
        )
        with pytest.raises(ValidationError, match="not WEBM"):
            async for chunk in stream:
                released.append(chunk)
        assert released == []

    async def test_more_than_the_cap_is_refused_as_it_arrives(self) -> None:
        stream = checked_stream(
            _chunks(WEBM, b"x" * 100, b"x" * 100), extension=".webm", max_bytes=200
        )
        with pytest.raises(ValidationError, match="File too large"):
            await _drain(stream)

    async def test_empty_file_is_refused(self) -> None:
        stream = checked_stream(_chunks(), extension=".webm", max_bytes=1000)
        with pytest.raises(ValidationError, match="empty"):
            await _drain(stream)


class TestPlaybackType:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("sessions/x/Recording 2026-10-01 10-00-00.webm", "audio/webm"),
            ("call.MP4", "audio/mp4"),
            ("call.mp3", "audio/mpeg"),
            ("call.wav", "audio/wav"),
            ("call.bin", "application/octet-stream"),
        ],
    )
    def test_the_player_type_follows_the_extension(
        self, name: str, expected: str
    ) -> None:
        assert playback_type(name) == expected
