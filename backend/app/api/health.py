import logging

from fastapi import APIRouter

from app.models.schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(deep: bool = False):
    if not deep:
        return HealthResponse(status="ok")

    checks: dict[str, str] = {}

    try:
        from app.rag.vectorstore import collection
        collection.count()
        checks["chromadb"] = "ok"
    except Exception:
        checks["chromadb"] = "chromadb_unavailable"
        logger.exception("Deep health check: ChromaDB failed")

    try:
        from app.core.clients import openai_client
        await openai_client.models.list()
        checks["openai"] = "ok"
    except Exception:
        checks["openai"] = "openai_unavailable"
        logger.exception("Deep health check: OpenAI failed")

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthResponse(status=status, checks=checks)
