import logging
import time

import chromadb
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.clients import openai_client
from app.core.config import settings
from app.rag.chunker import Chunk

logger = logging.getLogger(__name__)

_chroma = chromadb.PersistentClient(path=settings.chroma_persist_dir)
collection = _chroma.get_or_create_collection("legal_documents")

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
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        embeddings = await _embed([c.text for c in batch])
        collection.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            embeddings=embeddings,
            metadatas=[c.metadata for c in batch],
        )
    logger.info("Stored %d chunks in ChromaDB", len(chunks))


async def retrieve(question: str) -> list[dict]:
    start = time.time()
    q_embedding = (await _embed([question]))[0]
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=settings.retrieval_top_k,
        include=["documents", "metadatas", "distances"],
    )
    elapsed = time.time() - start

    chunks = []
    for cid, doc, meta, dist in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        if dist <= settings.retrieval_min_score:
            chunks.append({"chunk_id": cid, "text": doc, "metadata": meta})

    logger.info("Retrieval took %.2fs, returned %d/%d chunks (threshold=%.2f)", elapsed, len(chunks), len(results["ids"][0]), settings.retrieval_min_score)
    return chunks


async def delete_by_doc_id(doc_id: str) -> None:
    results = collection.get(where={"doc_id": doc_id}, include=[])
    if results["ids"]:
        collection.delete(ids=results["ids"])
        logger.info("Deleted %d chunks for doc %s", len(results["ids"]), doc_id)
