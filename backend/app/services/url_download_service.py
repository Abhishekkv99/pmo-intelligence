"""Fetch a session recording from a URL into PMO's media bucket.

Every request goes through the SSRF guard (``url_guard``): HTTPS only, every
redirect hop re-checked, and the connection pinned to the address that was
checked. The body is streamed straight into storage through the same type and
size checks as an upload (``media_files``), so nothing is buffered on disk or
in memory beyond one chunk and one storage part.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote

import httpx

from app.config import settings
from app.services.media_files import check_extension, checked_stream, extension_of
from app.services.storage import get_storage_backend
from app.services.storage.base import StorageBackend
from app.services.upload_service import session_media_key
from app.services.url_guard import Resolver, send_guarded, system_resolver
from app.utils.exceptions import DownloadError, ValidationError

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024

# MIME types that map to allowed extensions
MIME_TO_EXTENSION: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "audio/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
    "video/ogg": ".ogg",
}


@dataclass(frozen=True)
class UrlCheck:
    """What a pre-check learned about a URL before anything is downloaded."""

    filename: str
    content_type: str | None
    content_length: int | None


def _total_size_from_headers(headers: httpx.Headers, *, is_partial: bool) -> int | None:
    """Total file size from a Content-Range ('bytes 0-0/<total>') or Content-Length.

    On a 206 partial response, Content-Length is the slice size (not the total),
    so it is ignored unless Content-Range carries the real total.
    """
    content_range = headers.get("content-range")
    if content_range and "/" in content_range:
        total = content_range.rsplit("/", 1)[-1].strip()
        if total.isdigit():
            return int(total)
    if is_partial:
        return None
    content_length = headers.get("content-length")
    if content_length and content_length.isdigit():
        return int(content_length)
    return None


def _filename_from_url(url: httpx.URL) -> str:
    name = PurePosixPath(unquote(url.path)).name
    return name if "." in name else f"download-{uuid.uuid4().hex[:8]}"


class UrlDownloadService:
    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = system_resolver,
    ) -> None:
        self.storage = storage or get_storage_backend()
        self.transport = transport
        self.resolver = resolver
        self.max_bytes = settings.max_upload_size_mb * 1024 * 1024

    def _client(self, read_timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=30.0),
            transport=self.transport,
            follow_redirects=False,
        )

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, httpx.URL]:
        try:
            return await send_guarded(
                client,
                method,
                url,
                headers=headers,
                max_redirects=settings.url_download_max_redirects,
                resolver=self.resolver,
            )
        except httpx.TimeoutException as exc:
            raise DownloadError("The URL timed out") from exc
        except httpx.HTTPError as exc:
            raise DownloadError(f"Could not reach the URL: {exc}") from exc

    async def validate_url(self, url: str) -> UrlCheck:
        """Check the URL answers with an allowed recording type and size.

        Reads headers only: a HEAD, or for a server that refuses HEAD (a
        presigned GET URL), a streamed ``Range: bytes=0-0`` GET that is closed
        before its body is read.
        """
        async with self._client(30.0) as client:
            response, final_url = await self._send(client, "HEAD", url)
            await response.aclose()
            is_partial = False
            if response.status_code in (403, 405, 501):
                response, final_url = await self._send(
                    client, "GET", url, {"Range": "bytes=0-0"}
                )
                await response.aclose()
                is_partial = response.status_code == 206

        status = response.status_code
        if status in (401, 403):
            raise DownloadError(
                f"The URL requires sign-in (HTTP {status}). "
                "Only publicly readable URLs are supported."
            )
        if status >= 400:
            raise DownloadError(f"The URL answered HTTP {status}")

        headers = response.headers
        content_type = headers.get("content-type", "").split(";")[0].strip() or None
        content_length = _total_size_from_headers(headers, is_partial=is_partial)
        if content_length is not None and content_length > self.max_bytes:
            raise ValidationError(
                f"File too large ({content_length // (1024 * 1024)}MB). "
                f"Maximum: {settings.max_upload_size_mb}MB"
            )

        filename = _filename_from_url(final_url)
        if extension_of(filename) not in settings.allowed_extensions:
            if content_type in MIME_TO_EXTENSION:
                filename = (
                    PurePosixPath(filename).stem + MIME_TO_EXTENSION[content_type]
                )
            else:
                check_extension(filename, settings.allowed_extensions)
        return UrlCheck(filename, content_type, content_length)

    async def download_and_store(
        self, url: str, session_id: uuid.UUID, check: UrlCheck
    ) -> str:
        """Stream the recording into storage under the session's key; returns the key.

        A refused or failed download leaves nothing behind.
        """
        extension = check_extension(check.filename, settings.allowed_extensions)
        file_key = session_media_key(session_id, check.filename)
        try:
            async with asyncio.timeout(settings.url_download_timeout_seconds):
                await self._download(url, file_key, extension)
        except BaseException as exc:
            with contextlib.suppress(Exception):
                await self.storage.delete(file_key)
            if isinstance(exc, TimeoutError):
                raise DownloadError("The download took too long") from exc
            raise
        logger.info("Stored download for session %s as %s", session_id, file_key)
        return file_key

    async def _download(self, url: str, file_key: str, extension: str) -> None:
        async with self._client(60.0) as client:
            response, _ = await self._send(client, "GET", url)
            try:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"The download answered HTTP {response.status_code}"
                    )

                async def chunks() -> AsyncIterator[bytes]:
                    try:
                        async for chunk in response.aiter_bytes(CHUNK_SIZE):
                            yield chunk
                    except httpx.HTTPError as exc:
                        raise DownloadError(f"The download failed: {exc}") from exc

                stream = checked_stream(
                    chunks(), extension=extension, max_bytes=self.max_bytes
                )
                await self.storage.upload_stream(file_key, stream)
            finally:
                await response.aclose()
