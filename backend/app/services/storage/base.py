from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class StorageBackend(ABC):
    """Abstract base class for file storage backends."""

    @abstractmethod
    async def upload(self, file_key: str, data: bytes) -> str:
        """Store file data and return the storage key."""
        ...

    @abstractmethod
    async def upload_stream(self, file_key: str, stream: AsyncIterator[bytes]) -> str:
        """Store file from async stream (for large files)."""
        ...

    @abstractmethod
    async def download(self, file_key: str) -> bytes:
        """Download file data by key."""
        ...

    @abstractmethod
    async def delete(self, file_key: str) -> bool:
        """Delete file by key. Returns True if deleted."""
        ...

    @abstractmethod
    async def exists(self, file_key: str) -> bool:
        """Check if file exists."""
        ...

    @abstractmethod
    async def get_url(self, file_key: str, expires_in: int = 3600) -> str:
        """Get a URL/path to access the file."""
        ...
