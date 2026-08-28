"""MinIO / S3-compatible object storage client.

Phase 1 verifies connection, credentials and bucket availability only.
Evidence upload/download pipeline belongs to a later phase.
"""

from __future__ import annotations

import asyncio

import boto3
from app.core.config import Settings
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

DEFAULT_REGION = "us-east-1"


class Storage:
    """Thin S3-compatible wrapper configured for a local MinIO endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: BaseClient | None = None

    def client(self) -> BaseClient:
        if self._client is None:
            # MinIO reports an AWS Signature Version 4 mismatch unless we pin
            # the signing behaviour explicitly.
            self._client = boto3.client(
                "s3",
                endpoint_url=self._settings.S3_ENDPOINT,
                aws_access_key_id=self._settings.S3_ACCESS_KEY,
                aws_secret_access_key=self._settings.S3_SECRET_KEY,
                region_name=self._settings.S3_REGION or DEFAULT_REGION,
                config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 2}),
            )
        return self._client

    def bucket_name(self) -> str:
        return self._settings.S3_BUCKET

    def bucket_exists(self) -> bool:
        try:
            self.client().head_bucket(Bucket=self.bucket_name())
            return True
        except ClientError:
            return False

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist. Idempotent."""
        if self.bucket_exists():
            return
        self.client().create_bucket(Bucket=self.bucket_name())

    async def ping(self) -> None:
        """Raise if object storage is unreachable; used by the readiness check."""
        if not await asyncio.to_thread(self.bucket_exists):
            raise ConnectionError("object storage bucket is missing or inaccessible")

    def close(self) -> None:
        """Release the underlying client handle (no persistent sockets to drain)."""
        self._client = None

    def exists(self, key: str) -> bool:
        try:
            self.client().head_object(Bucket=self.bucket_name(), Key=key)
            return True
        except ClientError:
            return False

    def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client().put_object(
            Bucket=self.bucket_name(),
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def download(self, key: str) -> bytes:
        response = self.client().get_object(Bucket=self.bucket_name(), Key=key)
        body: StreamingBody = response["Body"]
        return body.read()

    def delete(self, key: str) -> None:
        self.client().delete_object(Bucket=self.bucket_name(), Key=key)
