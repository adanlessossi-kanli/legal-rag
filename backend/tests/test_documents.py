"""
REQ-QT-007: Delete endpoint removes document and its chunks.
"""
import pytest
from unittest.mock import patch, AsyncMock

from bson import ObjectId

from tests.conftest import TEST_USER_ID, _get_mock_db
from app.core import metadata


@pytest.mark.asyncio
async def test_delete_removes_document_and_chunks(client, auth_headers):
    """Insert a document + chunks, delete via API, verify both are gone."""
    db = _get_mock_db()
    uid = str(TEST_USER_ID)
    doc_id = "doc_del_test"

    # Seed document metadata
    await metadata.save_document(doc_id, "delete_me.pdf", 2, "ready", "hash_del", uid)

    # Seed chunks
    await db.chunks.insert_many([
        {"chunk_id": "c1", "doc_id": doc_id, "user_id": uid, "text": "chunk 1", "embedding": [], "metadata": {}},
        {"chunk_id": "c2", "doc_id": doc_id, "user_id": uid, "text": "chunk 2", "embedding": [], "metadata": {}},
    ])

    resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Document deleted"

    # Verify document metadata is gone
    assert await metadata.get_document(doc_id) is None

    # Verify chunks are gone
    remaining = await db.chunks.count_documents({"doc_id": doc_id})
    assert remaining == 0


def test_delete_nonexistent_returns_404(client, auth_headers):
    resp = client.delete("/api/documents/doc_nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_documents_returns_user_scoped(client, auth_headers):
    db = _get_mock_db()
    uid = str(TEST_USER_ID)
    other_uid = str(ObjectId())

    await metadata.save_document("doc_mine", "mine.pdf", 1, "ready", "h1", uid)
    await metadata.save_document("doc_other", "other.pdf", 1, "ready", "h2", other_uid)

    resp = client.get("/api/documents", headers=auth_headers)
    assert resp.status_code == 200
    ids = [d["id"] for d in resp.json()["items"]]
    assert "doc_mine" in ids
    assert "doc_other" not in ids


def test_documents_requires_auth(client):
    resp = client.get("/api/documents")
    assert resp.status_code == 401
