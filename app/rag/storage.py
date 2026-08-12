from __future__ import annotations

import io
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from minio import Minio

from app.core.config import settings
from app.core.resilience import resilient_tool


@resilient_tool(retries=3, circuit_name="minio_storage", fallback_message="MinIO 对象存储暂时不可用")
def _ensure_bucket(client: Minio, bucket: str) -> bool:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return True


@resilient_tool(retries=3, circuit_name="minio_storage", fallback_message="MinIO 对象写入失败")
def _put_object(client: Minio, bucket: str, key: str, content: bytes, content_type: str) -> str:
    client.put_object(bucket, key, io.BytesIO(content), len(content), content_type=content_type)
    return key


@resilient_tool(retries=3, circuit_name="minio_storage", fallback_message="MinIO 对象读取失败")
def _get_object(client: Minio, bucket: str, key: str) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


@resilient_tool(retries=3, circuit_name="minio_storage", fallback_message="MinIO 对象删除失败")
def _remove_object(client: Minio, bucket: str, key: str) -> bool:
    client.remove_object(bucket, key)
    return True


def _required(result, operation: str):
    if isinstance(result, str) and result.startswith("["):
        raise RuntimeError(f"{operation}: {result}")
    return result


def _create_minio_client(bucket: str) -> Minio:
    if not settings.minio_endpoint or not settings.minio_access_key or not settings.minio_secret_key:
        raise ValueError("MinIO endpoint and credentials are required")
    parsed = urlparse(
        settings.minio_endpoint
        if "://" in settings.minio_endpoint
        else f"http://{settings.minio_endpoint}"
    )
    client = Minio(
        parsed.netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=parsed.scheme == "https",
    )
    _required(_ensure_bucket(client, bucket), "ensure bucket")
    return client


class DocumentStorage:
    """Document blob storage backed by local disk or MinIO."""

    def __init__(self):
        self.backend = settings.object_storage_backend.lower().strip()
        self.root = Path(settings.document_storage_root)
        self.bucket = settings.minio_bucket_documents
        self.client: Minio | None = None
        if self.backend == "local":
            self.root.mkdir(parents=True, exist_ok=True)
            return
        if self.backend != "minio":
            raise ValueError(f"Unsupported object storage backend: {self.backend}")
        self.client = _create_minio_client(self.bucket)

    def _key(self, user_id: UUID | str, document_id: UUID | str, ext: str) -> str:
        return f"users/{user_id}/documents/{document_id}{ext}"

    def save(self, user_id: UUID | str, document_id: UUID | str, content: bytes, ext: str) -> str:
        key = self._key(user_id, document_id, ext)
        if self.backend == "local":
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return str(path)
        content_type = mimetypes.guess_type(f"file{ext}")[0] or "application/octet-stream"
        return _required(_put_object(self.client, self.bucket, key, content, content_type), "put object")

    def load(self, key: str) -> bytes:
        if self.backend == "local":
            return Path(key).read_bytes()
        return _required(_get_object(self.client, self.bucket, key), "get object")

    def delete(self, key: str) -> None:
        if self.backend == "local":
            Path(key).unlink(missing_ok=True)
            return
        _required(_remove_object(self.client, self.bucket, key), "remove object")

    def derived_key(self, user_id: UUID | str, document_id: UUID | str, ext: str) -> str:
        if self.backend == "local":
            return str(self.root / self._key(user_id, document_id, ext))
        return self._key(user_id, document_id, ext)

    def health_check(self) -> bool:
        if self.backend == "local":
            return self.root.exists()
        return bool(_required(_ensure_bucket(self.client, self.bucket), "health check"))


class TweetMediaStorage:
    """Original tweet image storage backed by local disk or MinIO."""

    def __init__(self):
        self.backend = settings.object_storage_backend.lower().strip()
        self.root = Path(settings.document_storage_root) / "tweet-media"
        self.bucket = settings.minio_bucket_tweet_media
        self.client: Minio | None = None
        if self.backend == "local":
            self.root.mkdir(parents=True, exist_ok=True)
            return
        if self.backend != "minio":
            raise ValueError(f"Unsupported object storage backend: {self.backend}")
        self.client = _create_minio_client(self.bucket)

    def save(
        self,
        tweet_external_id: str,
        content_hash: str,
        content: bytes,
        extension: str,
        content_type: str,
    ) -> str:
        key = f"tweets/{tweet_external_id}/{content_hash}{extension}"
        if self.backend == "local":
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return str(path)
        return _required(_put_object(self.client, self.bucket, key, content, content_type), "put object")

    def load(self, key: str) -> bytes:
        if self.backend == "local":
            return Path(key).read_bytes()
        return _required(_get_object(self.client, self.bucket, key), "get object")

    def delete(self, key: str) -> None:
        if self.backend == "local":
            Path(key).unlink(missing_ok=True)
            return
        _required(_remove_object(self.client, self.bucket, key), "remove object")

    def health_check(self) -> bool:
        if self.backend == "local":
            return self.root.exists()
        return bool(_required(_ensure_bucket(self.client, self.bucket), "health check"))
