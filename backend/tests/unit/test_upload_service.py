"""Uploading a session recording: streamed, capped, type-checked, cleaned up."""

import io
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.storage.local import LocalStorageBackend
from app.services.upload_service import UploadService, session_media_key
from app.utils.exceptions import ValidationError

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _upload(name: str, body: bytes, size: int | None = None) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(body),
        filename=name,
        size=len(body) if size is None else size,
        headers=Headers({"content-type": "application/octet-stream"}),
    )


@pytest.fixture
def service(tmp_path: Path) -> UploadService:
    return UploadService(storage=LocalStorageBackend(base_dir=str(tmp_path)))


def _stored(tmp_path: Path) -> list[Path]:
    return [p for p in tmp_path.rglob("*") if p.is_file()]


class TestSessionMediaKey:
    def test_key_is_under_the_session_with_a_clean_name(self) -> None:
        assert (
            session_media_key(SESSION_ID, "Recording 2026-10-01 10-00-00.webm")
            == f"sessions/{SESSION_ID}/Recording_2026-10-01_10-00-00.webm"
        )


class TestValidateFile:
    def test_missing_name_is_refused(self, service: UploadService) -> None:
        with pytest.raises(ValidationError, match="No file"):
            service.validate_file(_upload("", WEBM))

    def test_other_type_is_refused(self, service: UploadService) -> None:
        with pytest.raises(ValidationError, match="not allowed"):
            service.validate_file(_upload("notes.pdf", b"%PDF-1.7"))

    def test_declared_size_over_the_cap_is_refused_early(
        self, service: UploadService
    ) -> None:
        with pytest.raises(ValidationError, match="File too large"):
            service.validate_file(_upload("r.webm", WEBM, size=service.max_bytes + 1))


class TestStoreFile:
    async def test_recording_is_stored_under_the_session(
        self, service: UploadService, tmp_path: Path
    ) -> None:
        body = WEBM + b"audio" * 1000
        key = await service.store_file(_upload("call.webm", body), SESSION_ID)

        assert key == f"sessions/{SESSION_ID}/call.webm"
        assert (tmp_path / key).read_bytes() == body

    async def test_renamed_file_is_refused_and_nothing_is_kept(
        self, service: UploadService, tmp_path: Path
    ) -> None:
        with pytest.raises(ValidationError, match="not WEBM"):
            await service.store_file(
                _upload("call.webm", b"<html>a web page</html>" * 10), SESSION_ID
            )
        assert _stored(tmp_path) == []

    async def test_more_bytes_than_declared_are_stopped_at_the_cap(
        self, service: UploadService, tmp_path: Path
    ) -> None:
        service.max_bytes = 3 * 1024 * 1024
        body = WEBM + b"x" * (4 * 1024 * 1024)
        # The client claims a small file; the bytes that arrive decide.
        with pytest.raises(ValidationError, match="File too large"):
            await service.store_file(_upload("call.webm", body, size=10), SESSION_ID)
        assert _stored(tmp_path) == []
