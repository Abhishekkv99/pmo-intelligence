from collections.abc import AsyncIterator
from pathlib import Path

import aioboto3
import aiofiles

from app.config import settings
from app.services.storage.base import StorageBackend

CHUNK_SIZE = 8192


class LocalStorageBackend(StorageBackend):
    """Store files on the local filesystem."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)

    def _resolve_path(self, file_key: str) -> Path:
        return self.base_dir / file_key

    async def upload(self, file_key: str, data: bytes) -> str:
        path = self._resolve_path(file_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return file_key

    async def upload_stream(self, file_key: str, stream: AsyncIterator[bytes]) -> str:
        path = self._resolve_path(file_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            async for chunk in stream:
                await f.write(chunk)
        return file_key

    async def download(self, file_key: str) -> bytes:
        path = self._resolve_path(file_key)
        async with aiofiles.open(path, "rb") as f:
            data: bytes = await f.read()
        return data

    async def delete(self, file_key: str) -> bool:
        path = self._resolve_path(file_key)
        if not path.exists():
            return False
        path.unlink()
        return True

    async def exists(self, file_key: str) -> bool:
        return self._resolve_path(file_key).exists()

    async def get_url(
        self, file_key: str, expires_in: int = 3600, content_type: str | None = None
    ) -> str:
        return str(self._resolve_path(file_key))

    async def copy_from_s3(
        self, source_bucket: str, source_key: str, file_key: str
    ) -> str:
        """Stream the object down into a local file (development only)."""
        session = aioboto3.Session()
        async with session.client("s3", region_name=settings.aws_region) as s3:
            response = await s3.get_object(Bucket=source_bucket, Key=source_key)

            async def chunks() -> AsyncIterator[bytes]:
                while chunk := await response["Body"].read(1024 * 1024):
                    yield chunk

            await self.upload_stream(file_key, chunks())
        return file_key
