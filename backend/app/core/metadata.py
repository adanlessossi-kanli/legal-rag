import logging
from datetime import datetime, timezone

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


async def get_documents_paginated(user_id: str, org_id: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
    db = get_db()
    query = {"org_id": org_id} if org_id else {"user_id": user_id}
    total = await db.documents.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.documents.find(query).sort("uploaded_at", -1).skip(skip).limit(page_size)
    docs = []
    async for doc in cursor:
        docs.append({
            "id": doc["doc_id"],
            "name": doc["name"],
            "uploaded_at": doc["uploaded_at"],
            "chunk_count": doc["chunk_count"],
            "status": doc["status"],
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
