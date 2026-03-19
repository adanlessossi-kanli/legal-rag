import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.schemas import ConversationDetail, ConversationSummary, DeleteResponse, MessageOut

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.conversations.find({"user_id": user["_id"]}).sort("updated_at", -1)
    convos = []
    async for c in cursor:
        convos.append(ConversationSummary(id=str(c["_id"]), title=c["title"], updated_at=c["updated_at"]))
    return convos


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    convo = await db.conversations.find_one({"_id": ObjectId(conversation_id), "user_id": user["_id"]})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor = db.messages.find({"conversation_id": convo["_id"]}).sort("created_at", 1)
    messages = []
    async for m in cursor:
        messages.append(MessageOut(
            role=m["role"],
            content=m["content"],
            sources=m.get("sources", []),
            created_at=m["created_at"],
        ))

    return ConversationDetail(id=str(convo["_id"]), title=convo["title"], messages=messages)


@router.delete("/conversations/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = ObjectId(conversation_id)
    convo = await db.conversations.find_one({"_id": oid, "user_id": user["_id"]})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.messages.delete_many({"conversation_id": oid})
    await db.conversations.delete_one({"_id": oid})
    return DeleteResponse(detail="Conversation deleted")
