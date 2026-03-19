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


async def ingest(file_path: str, original_name: str, doc_id: str, content_hash: str) -> int:
    save_document(doc_id, original_name, 0, "processing", content_hash)
    try:
        pages = load_document(file_path)
        chunks = chunk_pages(pages, doc_id)
        await store_chunks(chunks)
        save_document(doc_id, original_name, len(chunks), "ready", content_hash)
        return len(chunks)
    except Exception:
        update_status(doc_id, "error")
        logger.exception("Ingestion failed for %s", original_name)
        raise


async def _resolve_query(question: str, history: list[ChatMessage]) -> str:
    if history and settings.enable_query_rewriting:
        return await rewrite_query(question, history)
    return question


async def query(question: str, history: list[ChatMessage]) -> tuple[str, list[Source]]:
    search_query = await _resolve_query(question, history)
    chunks = await retrieve(search_query)
    answer = await generate(question, chunks, history)
    sources = _build_sources(chunks)
    return answer, sources


async def query_stream(question: str, history: list[ChatMessage]) -> tuple[AsyncGenerator[str, None], list[Source]]:
    search_query = await _resolve_query(question, history)
    chunks = await retrieve(search_query)
    sources = _build_sources(chunks)
    return generate_stream(question, chunks, history), sources


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
