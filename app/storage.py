from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    bucket: str
    sha256: str
    size: int
    storage_backend: str


class Storage:
    def put(self, filename: str, content: bytes, content_type: str | None = None) -> StoredObject:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, filename: str, content: bytes, content_type: str | None = None) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        safe_name = Path(filename).name or "upload.bin"
        key = f"{digest[:12]}-{uuid4().hex}-{safe_name}"
        (self.root / key).write_bytes(content)
        return StoredObject(key=key, bucket=str(self.root), sha256=digest, size=len(content), storage_backend="local")

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3Storage(Storage):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3.")
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3.") from exc
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    def put(self, filename: str, content: bytes, content_type: str | None = None) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        safe_name = Path(filename).name or "upload.bin"
        key = f"uploads/{digest[:12]}-{uuid4().hex}-{safe_name}"
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, **extra)
        return StoredObject(key=key, bucket=self.bucket, sha256=digest, size=len(content), storage_backend="s3")

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend in {"s3", "r2", "supabase"}:
        return S3Storage()
    return LocalStorage(settings.local_storage_dir)
