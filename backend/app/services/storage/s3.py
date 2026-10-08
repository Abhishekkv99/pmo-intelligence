from collections.abc import AsyncIterator

import aioboto3
from botocore.exceptions import ClientError

from app.services.storage.base import StorageBackend
from app.services.storage.multipart import (
    EmptyStreamError,
    multipart_upload_from_stream,
)


class S3StorageBackend(StorageBackend):
    """S3 storage backend using aioboto3 for async operations."""

    def __init__(
        self,
        bucket_name: str,
        region: str,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict[str, str]:
        """Build kwargs for the S3 client context manager."""
        kwargs: dict[str, str] = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs

    async def upload(self, file_key: str, data: bytes) -> str:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=data,
            )
        return file_key

    async def upload_stream(self, file_key: str, stream: AsyncIterator[bytes]) -> str:
        """Stream to S3 as a multipart upload; only one part is ever in memory.

        Collecting the stream into one ``bytes`` object first held two copies of
        the whole file (up to 1 GB for a 500 MB upload) and was the largest
        transient allocation in the process.
        """
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            try:
                await multipart_upload_from_stream(
                    s3, bucket=self.bucket_name, key=file_key, chunks=stream
                )
            except EmptyStreamError:
                # Nothing arrived: store the empty object rather than nothing.
                await s3.put_object(Bucket=self.bucket_name, Key=file_key, Body=b"")
        return file_key

    async def download(self, file_key: str) -> bytes:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            response = await s3.get_object(
                Bucket=self.bucket_name,
                Key=file_key,
            )
            body: bytes = await response["Body"].read()
        return body

    async def delete(self, file_key: str) -> bool:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(
                Bucket=self.bucket_name,
                Key=file_key,
            )
        return True

    async def exists(self, file_key: str) -> bool:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    return False
                raise
        return True

    async def get_url(self, file_key: str, expires_in: int = 3600) -> str:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": file_key,
                },
                ExpiresIn=expires_in,
            )
        return url

    async def copy_from_s3(
        self, source_bucket: str, source_key: str, file_key: str
    ) -> str:
        """Server-side copy: the bytes never pass through this process.

        Works across accounts when the source bucket grants this role
        ``s3:GetObject`` (the PMO recordings bucket policy does). A single
        CopyObject handles objects up to 5 GB; recordings are about 125 MiB.
        """
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.copy_object(
                Bucket=self.bucket_name,
                Key=file_key,
                CopySource={"Bucket": source_bucket, "Key": source_key},
            )
        return file_key
