import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user, get_org_id
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintUpdate,
    PaginatedBlueprints,
)
from app.rag.vectorstore import _embed

logger = logging.getLogger(__name__)
router = APIRouter(tags=["blueprints"])


def _scope_query(user_id: str, org_id: str | None) -> dict:
    conditions: list[dict] = [{"user_id": "system", "is_default": True}]
    if org_id:
        conditions.append({"org_id": org_id})
    conditions.append({"user_id": user_id})
    return {"$or": conditions}


@router.post("/blueprints", response_model=BlueprintResponse, status_code=201)
async def create_blueprint(body: BlueprintCreate, user: dict = Depends(get_current_user)):
    org_id = get_org_id(user)
    db = get_db()

    import uuid
    blueprint_id = "bp_" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    doc = {
        "blueprint_id": blueprint_id,
        "name": body.name,
        "description": body.description,
        "content": body.content,
        "user_id": str(user["_id"]),
        "org_id": org_id or "",
        "is_default": False,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db.blueprints.insert_one(doc)
    except Exception as e:
        if "duplicate" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(409, "A blueprint with this name already exists")
        raise

    embedding = (await _embed([body.description]))[0]
    await db.chunks.insert_one({
        "chunk_id": blueprint_id,
        "doc_id": blueprint_id,
        "namespace": "ContextLibrary",
        "user_id": str(user["_id"]),
        "org_id": org_id or "",
        "text": body.description,
        "embedding": embedding,
        "metadata": {
            "source": body.name,
            "blueprint_id": blueprint_id,
            "namespace": "ContextLibrary",
        },
    })

    return BlueprintResponse(
        blueprint_id=blueprint_id,
        name=body.name,
        description=body.description,
        content=body.content,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


@router.get("/blueprints", response_model=PaginatedBlueprints)
async def list_blueprints(
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    user: dict = Depends(get_current_user),
):
    org_id = get_org_id(user)
    db = get_db()

    page_size = min(page_size, settings.max_page_size)
    skip = (page - 1) * page_size

    query = _scope_query(str(user["_id"]), org_id)
    total = await db.blueprints.count_documents(query)
    cursor = db.blueprints.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        items.append(BlueprintResponse(
            blueprint_id=doc["blueprint_id"],
            name=doc["name"],
            description=doc["description"],
            content=None,
            is_default=doc.get("is_default", False),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        ))

    return PaginatedBlueprints(items=items, total=total, page=page, page_size=page_size)


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(blueprint_id: str, user: dict = Depends(get_current_user)):
    org_id = get_org_id(user)
    db = get_db()

    query = {**_scope_query(str(user["_id"]), org_id), "blueprint_id": blueprint_id}
    doc = await db.blueprints.find_one(query)
    if not doc:
        raise HTTPException(404, "Blueprint not found")

    return BlueprintResponse(
        blueprint_id=doc["blueprint_id"],
        name=doc["name"],
        description=doc["description"],
        content=doc["content"],
        is_default=doc.get("is_default", False),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.put("/blueprints/{blueprint_id}", response_model=BlueprintResponse)
async def update_blueprint(blueprint_id: str, body: BlueprintUpdate, user: dict = Depends(get_current_user)):
    db = get_db()

    doc = await db.blueprints.find_one({"blueprint_id": blueprint_id})
    if not doc:
        raise HTTPException(404, "Blueprint not found")
    if doc.get("is_default"):
        raise HTTPException(403, "Default blueprints cannot be modified")
    if doc["user_id"] != str(user["_id"]):
        raise HTTPException(403, "Not authorized to modify this blueprint")

    update: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        update["name"] = body.name
    if body.description is not None:
        update["description"] = body.description
    if body.content is not None:
        update["content"] = body.content

    await db.blueprints.update_one({"blueprint_id": blueprint_id}, {"$set": update})

    if body.description is not None and body.description != doc["description"]:
        await db.chunks.delete_one({"chunk_id": blueprint_id, "namespace": "ContextLibrary"})
        embedding = (await _embed([body.description]))[0]
        await db.chunks.insert_one({
            "chunk_id": blueprint_id,
            "doc_id": blueprint_id,
            "namespace": "ContextLibrary",
            "user_id": doc["user_id"],
            "org_id": doc.get("org_id", ""),
            "text": body.description,
            "embedding": embedding,
            "metadata": {
                "source": update.get("name", doc["name"]),
                "blueprint_id": blueprint_id,
                "namespace": "ContextLibrary",
            },
        })

    updated = await db.blueprints.find_one({"blueprint_id": blueprint_id})
    return BlueprintResponse(
        blueprint_id=updated["blueprint_id"],
        name=updated["name"],
        description=updated["description"],
        content=updated["content"],
        is_default=updated.get("is_default", False),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.delete("/blueprints/{blueprint_id}", status_code=204)
async def delete_blueprint(blueprint_id: str, user: dict = Depends(get_current_user)):
    db = get_db()

    doc = await db.blueprints.find_one({"blueprint_id": blueprint_id})
    if not doc:
        raise HTTPException(404, "Blueprint not found")
    if doc.get("is_default"):
        raise HTTPException(403, "Default blueprints cannot be deleted")
    if doc["user_id"] != str(user["_id"]):
        raise HTTPException(403, "Not authorized to delete this blueprint")

    await db.blueprints.delete_one({"blueprint_id": blueprint_id})
    await db.chunks.delete_one({"chunk_id": blueprint_id, "namespace": "ContextLibrary"})
