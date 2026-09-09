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


def test_storage_list_and_case_scoped_delete(storage: Storage) -> None:
    storage.ensure_bucket()
    case_id = uuid.uuid4()
    other_case = uuid.uuid4()
    keys = [
        f"cases/{case_id}/evidence/{uuid.uuid4().hex}/a.csv",
        f"cases/{case_id}/evidence/{uuid.uuid4().hex}/b.csv",
        f"cases/{other_case}/evidence/{uuid.uuid4().hex}/c.csv",
    ]
    pre_existing = set(storage.list_keys("cases/"))
    try:
        for key in keys:
            storage.upload(key, b"payload")
        assert set(storage.list_keys(f"cases/{case_id}/")) == set(keys[:2])
        assert set(storage.list_keys("cases/")) - pre_existing == set(keys)

        removed = storage.delete_case_objects(case_id)
        assert removed == 2
        # the other case's object survives (A03: scoped, not global)
        assert set(storage.list_keys("cases/")) - pre_existing == {keys[2]}
        assert storage.exists(keys[2])
        # idempotent: nothing left for the deleted case
        assert storage.delete_case_objects(case_id) == 0
    finally:
        storage.delete_objects(keys)
