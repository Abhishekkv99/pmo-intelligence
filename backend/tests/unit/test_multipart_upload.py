"""Unit tests for the streaming multipart upload helper."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from app.services.storage.multipart import (
    DEFAULT_PART_SIZE,
    EmptyStreamError,
    multipart_upload_from_stream,
)

MIB = 1024 * 1024


def _client() -> AsyncMock:
    s3 = AsyncMock()
    s3.create_multipart_upload = AsyncMock(return_value={"UploadId": "u1"})
    s3.upload_part = AsyncMock(return_value={"ETag": "e"})
    s3.complete_multipart_upload = AsyncMock()
    s3.abort_multipart_upload = AsyncMock()
    return s3


async def _chunks(total_mib: int, chunk_mib: int) -> AsyncIterator[bytes]:
    for _ in range(total_mib // chunk_mib):
        yield b"x" * (chunk_mib * MIB)


class TestMultipartUploadFromStream:
    async def test_buffers_small_chunks_into_full_parts(self) -> None:
        s3 = _client()

        total = await multipart_upload_from_stream(
            s3, bucket="b", key="k", chunks=_chunks(20, 1)
        )

        assert total == 20 * MIB
        sizes = [len(c.kwargs["Body"]) for c in s3.upload_part.await_args_list]
        assert sizes == [DEFAULT_PART_SIZE, DEFAULT_PART_SIZE, 4 * MIB]
        numbers = [c.kwargs["PartNumber"] for c in s3.upload_part.await_args_list]
        assert numbers == [1, 2, 3]
        s3.complete_multipart_upload.assert_awaited_once_with(
            Bucket="b",
            Key="k",
            UploadId="u1",
            MultipartUpload={
                "Parts": [
                    {"PartNumber": 1, "ETag": "e"},
                    {"PartNumber": 2, "ETag": "e"},
                    {"PartNumber": 3, "ETag": "e"},
                ]
            },
        )
        s3.abort_multipart_upload.assert_not_awaited()
        s3.put_object.assert_not_awaited()

    async def test_stream_smaller_than_one_part_is_a_single_part(self) -> None:
        s3 = _client()

        await multipart_upload_from_stream(
            s3, bucket="b", key="k", chunks=_chunks(3, 1)
        )

        sizes = [len(c.kwargs["Body"]) for c in s3.upload_part.await_args_list]
        assert sizes == [3 * MIB]

    async def test_honours_a_custom_part_size(self) -> None:
        s3 = _client()

        await multipart_upload_from_stream(
            s3, bucket="b", key="k", chunks=_chunks(40, 1), part_size=16 * MIB
        )

        sizes = [len(c.kwargs["Body"]) for c in s3.upload_part.await_args_list]
        assert sizes == [16 * MIB, 16 * MIB, 8 * MIB]

    async def test_empty_stream_aborts_and_raises(self) -> None:
        s3 = _client()

        with pytest.raises(EmptyStreamError, match="empty"):
            await multipart_upload_from_stream(
                s3, bucket="b", key="k", chunks=_chunks(0, 1)
            )

        s3.complete_multipart_upload.assert_not_awaited()
        s3.abort_multipart_upload.assert_awaited_once_with(
            Bucket="b", Key="k", UploadId="u1"
        )

    async def test_part_failure_aborts_and_reraises(self) -> None:
        s3 = _client()
        s3.upload_part = AsyncMock(side_effect=RuntimeError("connection reset"))

        with pytest.raises(RuntimeError, match="connection reset"):
            await multipart_upload_from_stream(
                s3, bucket="b", key="k", chunks=_chunks(9, 1)
            )

        s3.complete_multipart_upload.assert_not_awaited()
        s3.abort_multipart_upload.assert_awaited_once()

    async def test_cancellation_mid_stream_aborts(self) -> None:
        """A worker cancelled at shutdown must not leave billable parts behind."""
        s3 = _client()

        async def _cancelled() -> AsyncIterator[bytes]:
            yield b"x" * (9 * MIB)
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await multipart_upload_from_stream(
                s3, bucket="b", key="k", chunks=_cancelled()
            )

        s3.abort_multipart_upload.assert_awaited_once()

    async def test_rejects_a_part_size_below_the_s3_floor(self) -> None:
        s3 = _client()

        with pytest.raises(ValueError, match="at least"):
            await multipart_upload_from_stream(
                s3, bucket="b", key="k", chunks=_chunks(1, 1), part_size=MIB
            )

        s3.create_multipart_upload.assert_not_awaited()
