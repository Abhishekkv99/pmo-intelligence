from pathlib import Path

import pytest

from app.services.storage.local import LocalStorageBackend


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(base_dir=str(tmp_path))


class TestLocalStorage:
    @pytest.mark.asyncio
    async def test_upload_creates_file(
        self, storage: LocalStorageBackend, tmp_path: Path
    ) -> None:
        key = await storage.upload("test/file.txt", b"hello world")
        assert key == "test/file.txt"
        assert (tmp_path / "test" / "file.txt").exists()

    @pytest.mark.asyncio
    async def test_download_returns_content(self, storage: LocalStorageBackend) -> None:
        await storage.upload("test.bin", b"binary data")
        content = await storage.download("test.bin")
        assert content == b"binary data"

    @pytest.mark.asyncio
    async def test_delete_removes_file(
        self, storage: LocalStorageBackend, tmp_path: Path
    ) -> None:
        await storage.upload("to_delete.txt", b"delete me")
        assert (tmp_path / "to_delete.txt").exists()
        result = await storage.delete("to_delete.txt")
        assert result is True
        assert not (tmp_path / "to_delete.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(
        self, storage: LocalStorageBackend
    ) -> None:
        result = await storage.delete("nonexistent.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, storage: LocalStorageBackend) -> None:
        await storage.upload("exists.txt", b"content")
        assert await storage.exists("exists.txt") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, storage: LocalStorageBackend) -> None:
        assert await storage.exists("nope.txt") is False

    @pytest.mark.asyncio
    async def test_get_url_returns_path(
        self, storage: LocalStorageBackend, tmp_path: Path
    ) -> None:
        await storage.upload("url_test.txt", b"content")
        url = await storage.get_url("url_test.txt")
        assert str(tmp_path / "url_test.txt") == url

    @pytest.mark.asyncio
    async def test_upload_stream(
        self, storage: LocalStorageBackend, tmp_path: Path
    ) -> None:
        async def stream():  # type: ignore[no-untyped-def]
            yield b"chunk1"
            yield b"chunk2"

        key = await storage.upload_stream("streamed.bin", stream())
        assert key == "streamed.bin"
        content = await storage.download("streamed.bin")
        assert content == b"chunk1chunk2"

    @pytest.mark.asyncio
    async def test_upload_creates_nested_dirs(
        self, storage: LocalStorageBackend, tmp_path: Path
    ) -> None:
        await storage.upload("a/b/c/deep.txt", b"deep")
        assert (tmp_path / "a" / "b" / "c" / "deep.txt").exists()
