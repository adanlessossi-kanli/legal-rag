import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import get_db
from app.core.metadata import update_status
from app.rag.pipeline import ingest

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


async def enqueue(file_path: str, original_name: str, doc_id: str, content_hash: str, user_id: str) -> None:
    db = get_db()
    await db.ingestion_queue.insert_one({
        "file_path": file_path,
        "original_name": original_name,
        "doc_id": doc_id,
        "content_hash": content_hash,
        "user_id": user_id,
        "status": "pending",
        "attempts": 0,
        "max_retries": settings.ingestion_max_retries,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "error": None,
    })
    logger.info("Enqueued ingestion for %s (%s)", doc_id, original_name)


async def _process_one(job: dict) -> None:
    db = get_db()
    doc_id = job["doc_id"]
    job_id = job["_id"]

    await db.ingestion_queue.update_one(
        {"_id": job_id},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}, "$inc": {"attempts": 1}},
    )

    try:
        await ingest(job["file_path"], job["original_name"], doc_id, job["content_hash"], job["user_id"])
        await db.ingestion_queue.update_one(
            {"_id": job_id},
            {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}},
        )
        logger.info("Ingestion completed for %s", doc_id)
    except Exception as e:
        attempts = job["attempts"] + 1
        if attempts >= job["max_retries"]:
            await db.ingestion_queue.update_one(
                {"_id": job_id},
                {"$set": {"status": "dead_letter", "error": str(e), "updated_at": datetime.now(timezone.utc)}},
            )
            await update_status(doc_id, "error")
            logger.error("Ingestion permanently failed for %s after %d attempts: %s", doc_id, attempts, e)
        else:
            await db.ingestion_queue.update_one(
                {"_id": job_id},
                {"$set": {"status": "pending", "error": str(e), "updated_at": datetime.now(timezone.utc)}},
            )
            logger.warning("Ingestion attempt %d failed for %s, will retry: %s", attempts, doc_id, e)


async def _worker_loop() -> None:
    while True:
        try:
            db = get_db()
            job = await db.ingestion_queue.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing"}},
                sort=[("created_at", 1)],
            )
            if job:
                await _process_one(job)
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Ingestion worker error")
            await asyncio.sleep(5)


async def start_worker() -> None:
    global _worker_task
    db = get_db()
    await db.ingestion_queue.create_index("status")
    await db.ingestion_queue.create_index([("status", 1), ("created_at", 1)])
    # Reset any jobs stuck in "processing" from a previous crash
    result = await db.ingestion_queue.update_many(
        {"status": "processing"},
        {"$set": {"status": "pending", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count:
        logger.info("Reset %d stuck ingestion jobs", result.modified_count)
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Ingestion worker started")


async def stop_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    logger.info("Ingestion worker stopped")
