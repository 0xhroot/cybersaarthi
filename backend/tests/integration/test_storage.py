"""Integration tests for MinIO / object storage connectivity.

These exercise the storage client directly. The S3 client is synchronous, so
the tests are sync functions.
"""

from __future__ import annotations

import uuid

from app.db.storage import Storage


def test_storage_connectivity_and_bucket(storage: Storage) -> None:
    storage.ensure_bucket()
    assert storage.bucket_exists()


def test_storage_upload_download_delete_round_trip(storage: Storage) -> None:
    key = f"test/{uuid.uuid4().hex}.txt"
    payload = b"phase-1 object storage round trip"

    storage.ensure_bucket()
    try:
        assert not storage.exists(key)
        storage.upload(key, payload, content_type="text/plain")
        assert storage.exists(key)
        assert storage.download(key) == payload
    finally:
        storage.delete(key)
        assert not storage.exists(key)
