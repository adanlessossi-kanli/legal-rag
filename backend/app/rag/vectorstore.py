import logging
import time

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.clients import openai_client
from app.core.config import settings
from app.core.database import get_db
from app.core.metrics import LLM_ERRORS, LLM_LATENCY, LLM_TOKENS, RETRIEVAL_CHUNKS, RETRIEVAL_LATENCY
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
    start = time.time()
    try:
        resp = await openai_client.embeddings.create(input=texts, model=settings.embedding_model)
    except Exception:
        LLM_ERRORS.labels("embedding").inc()
        raise
    LLM_LATENCY.labels("embedding").observe(time.time() - start)
    if resp.usage:
        LLM_TOKENS.labels("prompt").inc(resp.usage.total_tokens)
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
                "org_id": c.metadata.get("org_id", ""),
                "text": c.text,
                "embedding": emb,
                "metadata": c.metadata,
            }
            for c, emb in zip(batch, embeddings)
        ]
        await db.chunks.insert_many(docs)
    logger.info("Stored %d chunks in MongoDB", len(chunks))


def _build_scope_filter(user_id: str, document_ids: list[str] | None, org_id: str | None) -> dict:
    """Build a MongoDB filter dict for user/org/doc scoping."""
    f: dict = {}
    if org_id:
        f["org_id"] = org_id
    elif user_id:
        f["user_id"] = user_id
    if document_ids:
        f["doc_id"] = {"$in": document_ids}
    return f


async def _vector_search(question: str, user_id: str, document_ids: list[str] | None, org_id: str | None) -> list[dict]:
    """Semantic vector search via Atlas $vectorSearch."""
    db = get_db()
    q_embedding = (await _embed([question]))[0]
    vs_filter = _build_scope_filter(user_id, document_ids, org_id)

    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_search_index,
                "path": "embedding",
                "queryVector": q_embedding,
                "numCandidates": settings.retrieval_top_k * 10,
                "limit": settings.retrieval_top_k,
                **({"filter": vs_filter} if vs_filter else {}),
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
                "score": doc["score"],
            })
    return chunks


async def _keyword_search(question: str, user_id: str, document_ids: list[str] | None, org_id: str | None) -> list[dict]:
    """Full-text keyword search via MongoDB $text index."""
    db = get_db()
    scope = _build_scope_filter(user_id, document_ids, org_id)
    query_filter = {**scope, "$text": {"$search": question}}

    pipeline = [
        {"$match": query_filter},
        {"$addFields": {"score": {"$meta": "textScore"}}},
        {"$sort": {"score": -1}},
        {"$limit": settings.keyword_search_limit},
        {"$project": {"chunk_id": 1, "text": 1, "metadata": 1, "score": 1}},
    ]

    chunks = []
    async for doc in db.chunks.aggregate(pipeline):
        chunks.append({
            "chunk_id": doc["chunk_id"],
            "text": doc["text"],
            "metadata": doc["metadata"],
            "score": doc.get("score", 0.0),
        })
    return chunks


def _merge_results(vector_chunks: list[dict], keyword_chunks: list[dict], top_k: int) -> list[dict]:
    """Reciprocal Rank Fusion: merge vector and keyword results by chunk_id."""
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    k = 60  # RRF constant

    for rank, c in enumerate(vector_chunks):
        cid = c["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        by_id[cid] = c

    for rank, c in enumerate(keyword_chunks):
        cid = c["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        if cid not in by_id:
            by_id[cid] = c

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [by_id[cid] for cid, _ in ranked]


RERANK_PROMPT = (
    "You are a relevance judge. Given a question and a list of text passages, "
    "return ONLY a JSON array of passage indices (0-based) ordered from most "
    "relevant to least relevant. Include only passages that are relevant to the question. "
    "Return ONLY the JSON array, nothing else.\n\n"
    "Question: {question}\n\n"
    "Passages:\n{passages}"
)


@_retry
async def _rerank(question: str, chunks: list[dict]) -> list[dict]:
    """LLM-based reranking of retrieved chunks."""
    if len(chunks) <= 1:
        return chunks

    passages = "\n".join(f"[{i}] {c['text'][:500]}" for i, c in enumerate(chunks))
    prompt = RERANK_PROMPT.format(question=question, passages=passages)

    try:
        resp = await openai_client.chat.completions.create(
            model=settings.rerank_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        import json
        content = resp.choices[0].message.content.strip()
        indices = json.loads(content)
        if isinstance(indices, list):
            reranked = []
            seen = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(chunks) and idx not in seen:
                    reranked.append(chunks[idx])
                    seen.add(idx)
            if reranked:
                return reranked
    except Exception:
        logger.warning("Reranking failed, using original order", exc_info=True)

    return chunks


async def retrieve(question: str, user_id: str = "", document_ids: list[str] | None = None, org_id: str | None = None) -> list[dict]:
    start = time.time()

    # Vector search (always)
    vector_chunks = await _vector_search(question, user_id, document_ids, org_id)

    # Hybrid: merge with keyword search
    if settings.enable_hybrid_search and vector_chunks is not None:
        try:
            keyword_chunks = await _keyword_search(question, user_id, document_ids, org_id)
            chunks = _merge_results(vector_chunks, keyword_chunks, settings.retrieval_top_k)
        except Exception:
            logger.warning("Keyword search failed, using vector results only", exc_info=True)
            chunks = vector_chunks
    else:
        chunks = vector_chunks

    # Rerank
    if settings.enable_reranking and len(chunks) > 1:
        try:
            chunks = await _rerank(question, chunks)
        except Exception:
            logger.warning("Reranking failed, using fusion order", exc_info=True)

    elapsed = time.time() - start
    RETRIEVAL_LATENCY.observe(elapsed)
    RETRIEVAL_CHUNKS.observe(len(chunks))
    logger.info(
        "Retrieval took %.2fs, returned %d chunks (hybrid=%s, rerank=%s)",
        elapsed, len(chunks), settings.enable_hybrid_search, settings.enable_reranking,
    )
    return chunks


async def delete_by_doc_id(doc_id: str) -> None:
    db = get_db()
    result = await db.chunks.delete_many({"doc_id": doc_id})
    logger.info("Deleted %d chunks for doc %s", result.deleted_count, doc_id)
