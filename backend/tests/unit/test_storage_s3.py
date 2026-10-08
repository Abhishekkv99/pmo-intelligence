"""Unit tests for S3StorageBackend with mocked aioboto3."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.storage.s3 import S3StorageBackend

BUCKET = "test-bucket"
REGION = "us-east-1"
ENDPOINT = "http://localhost:9000"


def _make_backend(endpoint_url: str | None = None) -> S3StorageBackend:
    return S3StorageBackend(
        bucket_name=BUCKET,
        region=REGION,
        endpoint_url=endpoint_url,
    )


def _mock_s3_client() -> AsyncMock:
    """Create a mock S3 client that works as an async context manager."""
    mock_client = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=False)
    return mock_client, mock_context


class TestS3StorageBackendUpload:
    async def test_upload_calls_put_object_and_returns_key(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.upload("files/test.mp3", b"audio-data")

        assert result == "files/test.mp3"
        mock_client.put_object.assert_awaited_once_with(
            Bucket=BUCKET,
            Key="files/test.mp3",
            Body=b"audio-data",
        )

    async def test_upload_stream_sends_parts_without_joining(self) -> None:
        """20 MiB in 1 MiB chunks becomes three parts; the file is never joined."""
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()
        mock_client.create_multipart_upload.return_value = {"UploadId": "u1"}
        mock_client.upload_part.return_value = {"ETag": "e"}

        async def _stream() -> AsyncIterator[bytes]:
            for _ in range(20):
                yield b"x" * (1024 * 1024)

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.upload_stream("files/big.mp4", _stream())

        assert result == "files/big.mp4"
        mock_client.create_multipart_upload.assert_awaited_once_with(
            Bucket=BUCKET, Key="files/big.mp4"
        )
        sizes = [len(c.kwargs["Body"]) for c in mock_client.upload_part.await_args_list]
        assert sizes == [8 * 1024 * 1024, 8 * 1024 * 1024, 4 * 1024 * 1024]
        mock_client.complete_multipart_upload.assert_awaited_once()
        mock_client.put_object.assert_not_awaited()

    async def test_upload_stream_stores_an_empty_object_for_an_empty_stream(
        self,
    ) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()
        mock_client.create_multipart_upload.return_value = {"UploadId": "u1"}

        async def _stream() -> AsyncIterator[bytes]:
            return
            yield b""  # pragma: no cover - makes this an async generator

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.upload_stream("files/empty.mp4", _stream())

        assert result == "files/empty.mp4"
        mock_client.abort_multipart_upload.assert_awaited_once()
        mock_client.put_object.assert_awaited_once_with(
            Bucket=BUCKET, Key="files/empty.mp4", Body=b""
        )

    async def test_upload_stream_aborts_and_raises_on_a_failed_part(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()
        mock_client.create_multipart_upload.return_value = {"UploadId": "u1"}
        mock_client.upload_part.side_effect = RuntimeError("connection reset")

        async def _stream() -> AsyncIterator[bytes]:
            yield b"x" * (9 * 1024 * 1024)

        with (
            patch.object(backend._session, "client", return_value=mock_ctx),
            pytest.raises(RuntimeError),
        ):
            await backend.upload_stream("files/big.mp4", _stream())

        mock_client.abort_multipart_upload.assert_awaited_once()
        mock_client.complete_multipart_upload.assert_not_awaited()


class TestS3StorageBackendDownload:
    async def test_download_returns_file_bytes(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=b"file-content")
        mock_client.get_object.return_value = {"Body": mock_body}

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.download("files/test.mp3")

        assert result == b"file-content"
        mock_client.get_object.assert_awaited_once_with(
            Bucket=BUCKET,
            Key="files/test.mp3",
        )


class TestS3StorageBackendDelete:
    async def test_delete_calls_delete_object_and_returns_true(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.delete("files/test.mp3")

        assert result is True
        mock_client.delete_object.assert_awaited_once_with(
            Bucket=BUCKET,
            Key="files/test.mp3",
        )


class TestS3StorageBackendExists:
    async def test_exists_returns_true_when_object_found(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.exists("files/test.mp3")

        assert result is True
        mock_client.head_object.assert_awaited_once_with(
            Bucket=BUCKET,
            Key="files/test.mp3",
        )

    async def test_exists_returns_false_on_404(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.exists("files/missing.mp3")

        assert result is False

    async def test_exists_reraises_non_404_client_error(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()

        error_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        with (
            patch.object(backend._session, "client", return_value=mock_ctx),
            pytest.raises(ClientError),
        ):
            await backend.exists("files/forbidden.mp3")


class TestS3StorageBackendGetUrl:
    async def test_get_url_returns_presigned_url(self) -> None:
        backend = _make_backend()
        mock_client, mock_ctx = _mock_s3_client()
        mock_client.generate_presigned_url.return_value = (
            "https://bucket.s3.amazonaws.com/files/test.mp3?Signature=abc"
        )

        with patch.object(backend._session, "client", return_value=mock_ctx):
            result = await backend.get_url("files/test.mp3", expires_in=7200)

        assert "files/test.mp3" in result
        mock_client.generate_presigned_url.assert_awaited_once_with(
            "get_object",
            Params={"Bucket": BUCKET, "Key": "files/test.mp3"},
            ExpiresIn=7200,
        )


class TestS3StorageBackendConfig:
    def test_client_kwargs_without_endpoint(self) -> None:
        backend = _make_backend(endpoint_url=None)
        kwargs = backend._client_kwargs()
        assert kwargs == {"region_name": REGION}
        assert "endpoint_url" not in kwargs

    def test_client_kwargs_with_endpoint(self) -> None:
        backend = _make_backend(endpoint_url=ENDPOINT)
        kwargs = backend._client_kwargs()
        assert kwargs == {"region_name": REGION, "endpoint_url": ENDPOINT}
