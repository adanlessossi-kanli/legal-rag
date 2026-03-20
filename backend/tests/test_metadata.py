"""
REQ-QT-002: Metadata read/write round-trips correctly (MongoDB).
"""
import pytest

from tests.conftest import TEST_USER_ID, _get_mock_db
from app.core import metadata


@pytest.mark.asyncio
async def test_save_and_get():
    uid = str(TEST_USER_ID)
    await metadata.save_document("doc_1", "test.pdf", 10, "ready", "hash1", uid)
    doc = await metadata.get_document("doc_1")
    assert doc is not None
    assert doc["name"] == "test.pdf"
    assert doc["chunk_count"] == 10
    assert doc["status"] == "ready"


@pytest.mark.asyncio
async def test_get_all():
    uid = str(TEST_USER_ID)
    await metadata.save_document("doc_2", "a.pdf", 5, "ready", "hash2", uid)
    docs = await metadata.get_all_documents(uid)
    ids = [d["id"] for d in docs]
    assert "doc_2" in ids


@pytest.mark.asyncio
async def test_delete():
    uid = str(TEST_USER_ID)
    await metadata.save_document("doc_del", "del.pdf", 1, "ready", "hashd", uid)
    assert await metadata.delete_document("doc_del") is True
    assert await metadata.get_document("doc_del") is None


@pytest.mark.asyncio
async def test_delete_nonexistent():
    assert await metadata.delete_document("doc_nope") is False


@pytest.mark.asyncio
async def test_update_status():
    uid = str(TEST_USER_ID)
    await metadata.save_document("doc_s", "s.pdf", 1, "processing", "hashs", uid)
    await metadata.update_status("doc_s", "ready")
    doc = await metadata.get_document("doc_s")
    assert doc["status"] == "ready"


@pytest.mark.asyncio
async def test_find_by_hash():
    uid = str(TEST_USER_ID)
    await metadata.save_document("doc_h", "h.pdf", 1, "ready", "unique_hash", uid)
    found = await metadata.find_by_hash("unique_hash", uid)
    assert found is not None
    assert found["id"] == "doc_h"
    assert await metadata.find_by_hash("nonexistent", uid) is None
