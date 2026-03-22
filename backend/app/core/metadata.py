import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)


async def save_document(doc_id: str, name: str, chunk_count: int, status: str, content_hash: str = "", user_id: str = "", org_id: str = "") -> None:
    db = get_db()
    doc = {
        "doc_id": doc_id,
        "user_id": user_id,
        "name": name,
        "uploaded_at": datetime.now(timezone.utc),
        "chunk_count": chunk_count,
        "status": status,
        "content_hash": content_hash,
    }
    if org_id:
        doc["org_id"] = org_id
    await db.documents.update_one(
        {"doc_id": doc_id},
        {"$set": doc},
        upsert=True,
    )


async def get_all_documents(user_id: str, org_id: str | None = None) -> list[dict]:
    db = get_db()
    if org_id:
        query = {"org_id": org_id}
    else:
        query = {"user_id": user_id}
    cursor = db.documents.find(query).sort("uploaded_at", -1)
    docs = []
    async for doc in cursor:
        docs.append({
            "id": doc["doc_id"],
            "name": doc["name"],
            "uploaded_at": doc["uploaded_at"],
            "chunk_count": doc["chunk_count"],
            "status": doc["status"],
        })
    return docs


async def get_documents_paginated(
    user_id: str,
    org_id: str | None,
    page: int,
    page_size: int,
    search: str | None = None,
    status_filter: str | None = None,
    file_type: str | None = None,
    sort_by: str = "uploaded_at",
    sort_order: str = "desc",
) -> tuple[list[dict], int]:
    db = get_db()
    query: dict = {"org_id": org_id} if org_id else {"user_id": user_id}

    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if status_filter:
        query["status"] = status_filter
    if file_type:
        query["name"] = {**query.get("name", {}), "$regex": f"\\.{file_type}$", "$options": "i"}

    sort_dir = -1 if sort_order == "desc" else 1
    total = await db.documents.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.documents.find(query).sort(sort_by, sort_dir).skip(skip).limit(page_size)
    docs = []
    async for doc in cursor:
        docs.append({
            "id": doc["doc_id"],
            "name": doc["name"],
            "uploaded_at": doc["uploaded_at"],
            "chunk_count": doc["chunk_count"],
            "status": doc["status"],
            "version": doc.get("version", 1),
        })
    return docs, total


async def get_document(doc_id: str) -> dict | None:
    db = get_db()
    doc = await db.documents.find_one({"doc_id": doc_id})
    if not doc:
        return None
    return {
        "id": doc["doc_id"],
        "name": doc["name"],
        "uploaded_at": doc["uploaded_at"],
        "chunk_count": doc["chunk_count"],
        "status": doc["status"],
        "user_id": str(doc.get("user_id", "")),
        "org_id": str(doc.get("org_id", "")) if doc.get("org_id") else None,
    }


async def delete_document(doc_id: str) -> bool:
    db = get_db()
    result = await db.documents.delete_one({"doc_id": doc_id})
    return result.deleted_count > 0


async def update_status(doc_id: str, status: str) -> None:
    db = get_db()
    await db.documents.update_one({"doc_id": doc_id}, {"$set": {"status": status}})


async def find_by_hash(content_hash: str, user_id: str) -> dict | None:
    db = get_db()
    doc = await db.documents.find_one({"content_hash": content_hash, "user_id": user_id})
    if not doc:
        return None
    return {"id": doc["doc_id"], "name": doc["name"]}


# --- Document Versioning ---

async def save_version(doc_id: str, name: str, chunk_count: int, content_hash: str) -> int:
    """Save a version snapshot before re-upload. Returns the new version number."""
    if not settings.enable_document_versioning:
        return 1
    db = get_db()
    doc = await db.documents.find_one({"doc_id": doc_id})
    if not doc:
        return 1

    current_version = doc.get("version", 1)
    await db.document_versions.insert_one({
        "doc_id": doc_id,
        "version": current_version,
        "name": doc["name"],
        "chunk_count": doc["chunk_count"],
        "content_hash": doc.get("content_hash", ""),
        "uploaded_at": doc["uploaded_at"],
        "archived_at": datetime.now(timezone.utc),
    })

    # Prune old versions beyond max
    versions = await db.document_versions.count_documents({"doc_id": doc_id})
    if versions > settings.max_document_versions:
        oldest = db.document_versions.find({"doc_id": doc_id}).sort("version", 1).limit(versions - settings.max_document_versions)
        ids_to_delete = [v["_id"] async for v in oldest]
        if ids_to_delete:
            await db.document_versions.delete_many({"_id": {"$in": ids_to_delete}})

    return current_version + 1


async def get_document_versions(doc_id: str) -> list[dict]:
    """Get version history for a document."""
    db = get_db()
    cursor = db.document_versions.find({"doc_id": doc_id}).sort("version", -1)
    versions = []
    async for v in cursor:
        versions.append({
            "version": v["version"],
            "name": v["name"],
            "chunk_count": v["chunk_count"],
            "content_hash": v.get("content_hash", ""),
            "uploaded_at": v["uploaded_at"],
        })
    return versions
