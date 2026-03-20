import hashlib
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from app.core.config import settings
from app.core.metadata import save_document, update_status
from app.models.schemas import ChatMessage, Source
from app.rag.chunker import chunk_pages
from app.rag.llm import generate, generate_stream, rewrite_query
from app.rag.loader import load_document
from app.rag.vectorstore import delete_by_doc_id, retrieve, store_chunks

logger = logging.getLogger(__name__)

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your uploaded documents to answer this question. "
    "Try uploading more documents or rephrasing your question."
)


async def ingest(file_path: str, original_name: str, doc_id: str, content_hash: str, user_id: str = "") -> int:
    await save_document(doc_id, original_name, 0, "processing", content_hash, user_id)
    try:
        pages = load_document(file_path)
        chunks = chunk_pages(pages, doc_id)
        for c in chunks:
            c.metadata["user_id"] = user_id
        await store_chunks(chunks)
        await save_document(doc_id, original_name, len(chunks), "ready", content_hash, user_id)
        return len(chunks)
    except Exception:
        await update_status(doc_id, "error")
        logger.exception("Ingestion failed for %s", original_name)
        raise


async def _resolve_query(question: str, history: list[ChatMessage]) -> str:
    if history and settings.enable_query_rewriting:
        return await rewrite_query(question, history)
    return question


async def query(question: str, history: list[ChatMessage], user_id: str = "", document_ids: list[str] | None = None) -> tuple[str, list[Source], bool]:
    search_query = await _resolve_query(question, history)
    chunks = await retrieve(search_query, user_id, document_ids)
    if not chunks:
        return NO_CONTEXT_ANSWER, [], True
    answer = await generate(question, chunks, history)
    sources = _build_sources(chunks)
    return answer, sources, False


async def query_stream(question: str, history: list[ChatMessage], user_id: str = "", document_ids: list[str] | None = None) -> tuple[AsyncGenerator[str, None] | None, list[Source], bool]:
    search_query = await _resolve_query(question, history)
    chunks = await retrieve(search_query, user_id, document_ids)
    if not chunks:
        return None, [], True
    sources = _build_sources(chunks)
    return generate_stream(question, chunks, history), sources, False


def _build_sources(chunks: list[dict]) -> list[Source]:
    return [
        Source(
            document=c["metadata"].get("source", "unknown"),
            chunk_id=c["chunk_id"],
            text=c["text"][: settings.source_text_max_length],
        )
        for c in chunks
    ]


async def remove_document(doc_id: str) -> None:
    await delete_by_doc_id(doc_id)
    file_dir = Path(settings.upload_dir)
    for f in file_dir.iterdir():
        if f.name.startswith(doc_id):
            f.unlink()
            break


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
