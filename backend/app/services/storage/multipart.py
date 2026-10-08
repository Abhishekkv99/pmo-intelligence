"""Stream an async byte iterator into S3 as a multipart upload.

One part is in memory at a time. Every caller that used to collect a whole
file into a single ``bytes`` object before ``put_object`` (a 500 MB upload held
1 GB live: the chunk list plus the joined copy) now sends ``part_size`` at a
time and never holds more than about two parts' worth of bytes. Large transient
allocations are what glibc's allocator fails to return to the OS, so bounding
them is the first line of defence against the backend's RSS ratcheting up with
every recording processed.
"""

from collections.abc import AsyncIterator
from typing import Any

# S3 refuses a multipart upload whose non-final parts are under 5 MiB.
S3_MIN_PART_SIZE = 5 * 1024 * 1024
DEFAULT_PART_SIZE = 8 * 1024 * 1024


class EmptyStreamError(ValueError):
    """The stream produced no bytes, so there was nothing to upload."""


async def multipart_upload_from_stream(
    s3: Any,
    *,
    bucket: str,
    key: str,
    chunks: AsyncIterator[bytes],
    part_size: int = DEFAULT_PART_SIZE,
) -> int:
    """Upload ``chunks`` to ``s3://bucket/key`` as a multipart upload.

    Chunks may be any size: they are buffered up to ``part_size`` before each
    part is sent, because S3 rejects non-final parts below 5 MiB and a network
    read returns *up to* the requested size, never a guaranteed amount. The
    final part is the only one allowed to be short.

    Each part is copied out of the buffer exactly once (``bytes(memoryview)``
    rather than slicing the bytearray and then converting it, which copies
    twice), so the transient peak is about two parts, not three.

    The upload is aborted on any exception, including cancellation, so a task
    killed mid-upload does not leave billable parts behind. Returns the number
    of bytes uploaded. Raises ``EmptyStreamError`` for a stream that yields no
    bytes, since S3 will not complete a multipart upload with zero parts.
    """
    if part_size < S3_MIN_PART_SIZE:
        raise ValueError(f"part_size must be at least {S3_MIN_PART_SIZE} bytes")

    upload = await s3.create_multipart_upload(Bucket=bucket, Key=key)
    upload_id = upload["UploadId"]
    parts: list[dict[str, object]] = []
    total = 0

    async def _send(payload: bytes) -> None:
        number = len(parts) + 1
        resp = await s3.upload_part(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=number,
            Body=payload,
        )
        parts.append({"PartNumber": number, "ETag": resp["ETag"]})

    try:
        buffer = bytearray()
        async for chunk in chunks:
            buffer.extend(chunk)
            total += len(chunk)
            while len(buffer) >= part_size:
                await _send(bytes(memoryview(buffer)[:part_size]))
                del buffer[:part_size]

        if buffer:
            await _send(bytes(buffer))

        if not parts:
            raise EmptyStreamError(f"Source stream is empty: s3://{bucket}/{key}")

        await s3.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except BaseException:
        await s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        raise

    return total
