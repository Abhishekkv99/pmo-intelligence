"""Store an uploaded session recording in PMO's media bucket.

The upload is streamed in 1 MiB chunks with a running byte cap and a
signature check (``media_files``), so a 250 MiB recording is never held in
memory and a file larger than the cap is stopped as soon as it passes it,
whatever size the client declared.
"""

import contextlib
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import UploadFile

from app.config import settings
from app.services.media_files import check_extension, checked_stream, sanitize_filename
from app.services.storage import get_storage_backend
from app.services.storage.base import StorageBackend
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)

# 1 MiB reads: a 500 MB upload is ~500 awaits instead of ~64,000 at 8 KiB
CHUNK_SIZE = 1024 * 1024


def session_media_key(session_id: uuid.UUID, filename: str) -> str:
    """Where a session's recording lives in the media bucket."""
    return f"sessions/{session_id}/{sanitize_filename(filename)}"


class UploadService:
    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()
        self.max_bytes = settings.max_upload_size_mb * 1024 * 1024

    def validate_file(self, file: UploadFile) -> str:
        """Check the name, extension and declared size; returns the extension.

        The declared size is only an early refusal; ``store_file`` counts the
        bytes that actually arrive.
        """
        if not file.filename:
            raise ValidationError("No file provided")
        extension = check_extension(file.filename, settings.allowed_extensions)
        if file.size is not None and file.size > self.max_bytes:
            raise ValidationError(
                f"File too large. Maximum: {settings.max_upload_size_mb}MB"
            )
        return extension

    async def store_file(self, file: UploadFile, session_id: uuid.UUID) -> str:
        """Stream the upload to storage under the session's key; returns the key.

        A refused or failed upload leaves nothing behind: S3 aborts the
        multipart upload, and a partial local file is deleted here.
        """
        extension = self.validate_file(file)
        file_key = session_media_key(session_id, file.filename or "recording")

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await file.read(CHUNK_SIZE):
                yield chunk

        stream = checked_stream(chunks(), extension=extension, max_bytes=self.max_bytes)
        try:
            await self.storage.upload_stream(file_key, stream)
        except BaseException:
            with contextlib.suppress(Exception):
                await self.storage.delete(file_key)
            raise
        logger.info("Stored upload for session %s as %s", session_id, file_key)
        return file_key
