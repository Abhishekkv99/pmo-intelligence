"""Fetching a session recording from a URL, through the SSRF guard."""

import uuid
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.services.storage.local import LocalStorageBackend
from app.services.url_download_service import UrlCheck, UrlDownloadService
from app.utils.exceptions import DownloadError, ValidationError

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
URL = "https://media.example.com/calls/Recording%202026-10-01.webm"


async def _public(host: str, port: int) -> list[str]:
    return {"media.example.com": ["93.184.215.14"], "internal.example": ["10.0.0.5"]}[
        host
    ]


def _service(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> UrlDownloadService:
    return UrlDownloadService(
        storage=LocalStorageBackend(base_dir=str(tmp_path)),
        transport=httpx.MockTransport(handler),
        resolver=_public,
    )


def _stored(tmp_path: Path) -> list[Path]:
    return [p for p in tmp_path.rglob("*") if p.is_file()]


class TestValidateUrl:
    async def test_head_gives_name_type_and_size(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "HEAD"
            return httpx.Response(
                200, headers={"content-type": "video/webm", "content-length": "5000"}
            )

        check = await _service(tmp_path, handler).validate_url(URL)
        assert check == UrlCheck("Recording 2026-10-01.webm", "video/webm", 5000)

    async def test_head_refused_falls_back_to_a_one_byte_ranged_get(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "HEAD":
                return httpx.Response(403)
            assert request.headers["range"] == "bytes=0-0"
            return httpx.Response(
                206,
                headers={
                    "content-type": "video/webm",
                    "content-length": "1",
                    "content-range": "bytes 0-0/7340032",
                },
            )

        check = await _service(tmp_path, handler).validate_url(URL)
        assert check.content_length == 7340032

    async def test_declared_size_over_the_cap_is_refused(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-length": str(10**12)})

        with pytest.raises(ValidationError, match="File too large"):
            await _service(tmp_path, handler).validate_url(URL)

    async def test_url_needing_sign_in_is_refused(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        with pytest.raises(DownloadError, match="requires sign-in"):
            await _service(tmp_path, handler).validate_url(URL)

    async def test_name_without_extension_takes_it_from_the_content_type(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "audio/mpeg"})

        check = await _service(tmp_path, handler).validate_url(
            "https://media.example.com/download?id=7"
        )
        assert check.filename.endswith(".mp3")

    async def test_unsupported_type_is_refused(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"})

        with pytest.raises(ValidationError, match="not allowed"):
            await _service(tmp_path, handler).validate_url(
                "https://media.example.com/page.html"
            )

    async def test_internal_address_is_refused_before_any_request(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request may be sent")

        with pytest.raises(ValidationError, match="private or internal"):
            await _service(tmp_path, handler).validate_url(
                "https://internal.example/r.webm"
            )


class TestDownloadAndStore:
    CHECK = UrlCheck("Recording 2026-10-01.webm", "video/webm", None)

    async def test_recording_is_streamed_into_the_session_key(
        self, tmp_path: Path
    ) -> None:
        body = WEBM + b"audio" * 1000

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        key = await _service(tmp_path, handler).download_and_store(
            URL, SESSION_ID, self.CHECK
        )
        assert key == f"sessions/{SESSION_ID}/Recording_2026-10-01.webm"
        assert (tmp_path / key).read_bytes() == body

    async def test_web_page_instead_of_a_recording_is_refused_and_not_kept(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>Sign in to continue</html>")

        with pytest.raises(ValidationError, match="not WEBM"):
            await _service(tmp_path, handler).download_and_store(
                URL, SESSION_ID, self.CHECK
            )
        assert _stored(tmp_path) == []

    async def test_body_over_the_cap_is_stopped_and_not_kept(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=WEBM + b"x" * 4096)

        service = _service(tmp_path, handler)
        service.max_bytes = 1024
        with pytest.raises(ValidationError, match="File too large"):
            await service.download_and_store(URL, SESSION_ID, self.CHECK)
        assert _stored(tmp_path) == []

    async def test_error_status_is_a_download_error(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        with pytest.raises(DownloadError, match="HTTP 404"):
            await _service(tmp_path, handler).download_and_store(
                URL, SESSION_ID, self.CHECK
            )

    async def test_redirect_to_an_internal_address_is_refused(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302, headers={"location": "https://internal.example/r.webm"}
            )

        with pytest.raises(ValidationError, match="private or internal"):
            await _service(tmp_path, handler).download_and_store(
                URL, SESSION_ID, self.CHECK
            )
        assert _stored(tmp_path) == []
