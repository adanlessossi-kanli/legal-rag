import logging
import time

from bson import ObjectId
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.clients import openai_client
from app.core.config import settings
from app.core.database import get_db
from app.rag.chunker import Chunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

_retry = retry(
    stop=stop_after_attempt(settings.openai_max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
)


@_retry
async def _embed(texts: list[str]) -> list[list[float]]:
    resp = await openai_client.embeddings.create(input=texts, model=settings.embedding_model)
    return [e.embedding for e in resp.data]


async def store_chunks(chunks: list[Chunk]) -> None:
    db = get_db()
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        embeddings = await _embed([c.text for c in batch])
        docs = [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.metadata.get("doc_id", ""),
                "user_id": c.metadata.get("user_id", ""),
                "text": c.text,
                "embedding": emb,
                "metadata": c.metadata,
            }
            for c, emb in zip(batch, embeddings)
        ]
        await db.chunks.insert_many(docs)
    logger.info("Stored %d chunks in MongoDB", len(chunks))


async def retrieve(question: str, user_id: str = "", document_ids: list[str] | None = None) -> list[dict]:
    start = time.time()
    db = get_db()
    q_embedding = (await _embed([question]))[0]

    vs_filter = {}
    if user_id:
        vs_filter["user_id"] = user_id
    if document_ids:
        vs_filter["doc_id"] = {"$in": document_ids}

    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_search_index,
                "path": "embedding",
                "queryVector": q_embedding,
                "numCandidates": settings.retrieval_top_k * 10,
                "limit": settings.retrieval_top_k,
                **({
                    "filter": vs_filter} if vs_filter else {}),
            }
        },
        {
            "$project": {
                "chunk_id": 1,
                "text": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    chunks = []
    async for doc in db.chunks.aggregate(pipeline):
        if doc["score"] >= settings.retrieval_min_score:
            chunks.append({
                "chunk_id": doc["chunk_id"],
                "text": doc["text"],
                "metadata": doc["metadata"],
            })

    elapsed = time.time() - start
    logger.info("Retrieval took %.2fs, returned %d chunks (threshold=%.2f)", elapsed, len(chunks), settings.retrieval_min_score)
    return chunks


async def delete_by_doc_id(doc_id: str) -> None:
    db = get_db()
    result = await db.chunks.delete_many({"doc_id": doc_id})
    logger.info("Deleted %d chunks for doc %s", result.deleted_count, doc_id)
