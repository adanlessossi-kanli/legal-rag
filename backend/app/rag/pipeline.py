import hashlib
import logging
from collections.abc import AsyncGenerator

from app.agents import get_orchestrator
from app.agents.base import StatusCallback
from app.models.schemas import ChatMessage, Source

logger = logging.getLogger(__name__)

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your uploaded documents to answer this question. "
    "Try uploading more documents or rephrasing your question."
)


async def ingest(file_path: str, original_name: str, doc_id: str, content_hash: str, user_id: str = "") -> int:
    return await get_orchestrator().ingest(file_path, original_name, doc_id, content_hash, user_id)


async def query(
    question: str,
    history: list[ChatMessage],
    user_id: str = "",
    document_ids: list[str] | None = None,
    on_status: StatusCallback | None = None,
) -> tuple[str, list[Source], bool]:
    return await get_orchestrator().query(question, history, user_id, document_ids, on_status)


async def query_stream(
    question: str,
    history: list[ChatMessage],
    user_id: str = "",
    document_ids: list[str] | None = None,
    on_status: StatusCallback | None = None,
) -> tuple[AsyncGenerator[str, None] | None, list[Source], bool]:
    return await get_orchestrator().query_stream(question, history, user_id, document_ids, on_status)


async def remove_document(doc_id: str) -> None:
    await get_orchestrator().remove_document(doc_id)


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
