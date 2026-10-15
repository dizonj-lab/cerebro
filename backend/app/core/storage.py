"""Object storage for artifact bytes.

The service layer never names a provider. Two backends implement one
protocol: the filesystem for local development and tests, S3 (MinIO) for
compose and Kubernetes. This mirrors the PoC contract, where an artifact
records a `storage_uri` rather than a path.
"""
from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings


class ObjectStore(ABC):
    """Content-addressed blob storage. Keys are opaque to callers."""

    @abstractmethod
    def put(self, key: str, content: bytes) -> str:
        """Store bytes and return the storage URI that locates them."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the stored bytes, or raise FileNotFoundError."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object. Missing objects are not an error."""


class FilesystemObjectStore(ObjectStore):
    """Local disk. Used for development and the test suite."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are generated server-side, never taken from a client, but
        # resolve anyway so a crafted key cannot escape the root.
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Refusing to write outside the storage root")
        return path

    def put(self, key: str, content: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"file://{path}"

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3ObjectStore(ObjectStore):
    """S3-compatible storage, used with MinIO.

    boto3 is imported lazily so the dependency is only required where this
    backend is actually configured.
    """

    def __init__(self, *, endpoint: str, bucket: str, access_key: str, secret_key: str,
                 region: str = "us-east-1", secure: bool = False) -> None:
        import boto3

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if secure else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, content: bytes) -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=content)
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise FileNotFoundError(key) from exc

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    """Return the configured store, built once per process."""
    global _store
    if _store is not None:
        return _store

    settings = get_settings()
    if settings.storage_backend == "s3":
        _store = S3ObjectStore(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )
    else:
        _store = FilesystemObjectStore(settings.storage_path)
    return _store


def reset_object_store() -> None:
    """Drop the cached store. Used by tests."""
    global _store
    _store = None


def clear_filesystem_store(root: str | Path) -> None:
    """Remove every stored object. Used by tests."""
    shutil.rmtree(Path(root), ignore_errors=True)
