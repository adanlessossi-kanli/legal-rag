import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import verify_api_key
from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import query, query_stream

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_api_key)])
limiter = Limiter(key_func=get_remote_address)


def _truncate_history(req: ChatRequest) -> list:
    history = req.history
    if len(history) > settings.max_history_messages:
        logger.warning("Truncating history from %d to %d messages", len(history), settings.max_history_messages)
        history = history[-settings.max_history_messages:]
    return history


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.rate_limit_chat)
async def chat(request: Request, req: ChatRequest):
    history = _truncate_history(req)
    stream = request.query_params.get("stream", "").lower() == "true"

    try:
        if stream:
            return await _stream_response(req.question, history)
        answer, sources = await query(req.question, history)
        return ChatResponse(answer=answer, sources=sources)
    except Exception:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail="Failed to generate answer")


async def _stream_response(question: str, history: list) -> StreamingResponse:
    token_gen, sources = await query_stream(question, history)

    async def event_stream():
        # Send sources first so the client has them before tokens arrive
        sources_data = [s.model_dump() for s in sources]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
        async for token in token_gen:
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
