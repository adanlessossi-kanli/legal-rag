import asyncio
import json
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import ChatMessage, ChatRequest, ChatResponse, Source
from app.rag.pipeline import NO_CONTEXT_ANSWER, query, query_stream

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])
limiter = Limiter(key_func=get_remote_address)


async def _load_history(conversation_id: str, user_id: ObjectId) -> list[ChatMessage]:
    db = get_db()
    convo = await db.conversations.find_one({"_id": ObjectId(conversation_id), "user_id": user_id})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor = db.messages.find({"conversation_id": convo["_id"]}).sort("created_at", 1)
    messages = []
    async for m in cursor:
        messages.append(ChatMessage(role=m["role"], content=m["content"]))

    if len(messages) > settings.max_history_messages:
        messages = messages[-settings.max_history_messages:]
    return messages


async def _create_conversation(user_id: ObjectId, question: str) -> str:
    db = get_db()
    now = datetime.now(timezone.utc)
    result = await db.conversations.insert_one({
        "user_id": user_id,
        "title": question[:80],
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)


async def _save_message(conversation_id: str, user_id: ObjectId, role: str, content: str, sources: list | None = None) -> None:
    db = get_db()
    oid = ObjectId(conversation_id)
    await db.messages.insert_one({
        "conversation_id": oid,
        "user_id": user_id,
        "role": role,
        "content": content,
        "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in (sources or [])],
        "created_at": datetime.now(timezone.utc),
    })
    await db.conversations.update_one({"_id": oid}, {"$set": {"updated_at": datetime.now(timezone.utc)}})


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.rate_limit_chat)
async def chat(request: Request, req: ChatRequest, user: dict = Depends(get_current_user)):
    user_id = user["_id"]
    stream = request.query_params.get("stream", "").lower() == "true"

    conversation_id = req.conversation_id
    if conversation_id:
        history = await _load_history(conversation_id, user_id)
    else:
        conversation_id = await _create_conversation(user_id, req.question)
        history = []

    await _save_message(conversation_id, user_id, "user", req.question)

    try:
        if stream:
            return await _stream_response(req.question, history, conversation_id, user_id, req.document_ids)
        answer, sources, no_context = await query(req.question, history, str(user_id), req.document_ids)
        await _save_message(conversation_id, user_id, "assistant", answer, sources)
        return ChatResponse(answer=answer, sources=sources, conversation_id=conversation_id, no_context=no_context)
    except Exception:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail="Failed to generate answer")


async def _stream_response(question: str, history: list, conversation_id: str, user_id: ObjectId, document_ids: list[str] | None = None) -> StreamingResponse:
    status_queue: asyncio.Queue = asyncio.Queue()

    async def on_status(agent: str, status: str) -> None:
        await status_queue.put({"type": "agent_status", "agent": agent, "status": status})

    token_gen, sources, no_context = await query_stream(question, history, str(user_id), document_ids, on_status)

    async def event_stream():
        # Drain any status events emitted during research phase
        while not status_queue.empty():
            evt = await status_queue.get()
            yield f"data: {json.dumps(evt)}\n\n"

        sources_data = [s.model_dump() for s in sources]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

        # Drain status events emitted after sources (writer working)
        while not status_queue.empty():
            evt = await status_queue.get()
            yield f"data: {json.dumps(evt)}\n\n"

        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"

        if no_context:
            yield f"data: {json.dumps({'type': 'token', 'token': NO_CONTEXT_ANSWER})}\n\n"
            await _save_message(conversation_id, user_id, "assistant", NO_CONTEXT_ANSWER, [])
        else:
            full_answer = []
            async for token in token_gen:
                full_answer.append(token)
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            await _save_message(conversation_id, user_id, "assistant", "".join(full_answer), sources)

        # Drain final status events (done)
        while not status_queue.empty():
            evt = await status_queue.get()
            yield f"data: {json.dumps(evt)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
