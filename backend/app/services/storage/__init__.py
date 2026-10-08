from app.config import settings
from app.services.storage.base import StorageBackend
from app.services.storage.local import LocalStorageBackend


def get_storage_backend() -> StorageBackend:
    """Factory: return storage backend based on config."""
    if settings.storage_backend == "s3":
        from app.services.storage.s3 import S3StorageBackend

        return S3StorageBackend(
            bucket_name=settings.s3_bucket_name,
            region=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
        )
    return LocalStorageBackend(base_dir=settings.local_upload_dir)
