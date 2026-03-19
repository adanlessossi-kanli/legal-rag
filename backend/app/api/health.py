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
        from app.core.database import get_db
        db = get_db()
        await db.command("ping")
        checks["mongodb"] = "ok"
    except Exception:
        checks["mongodb"] = "mongodb_unavailable"
        logger.exception("Deep health check: MongoDB failed")

    try:
        from app.core.clients import openai_client
        await openai_client.models.list()
        checks["openai"] = "ok"
    except Exception:
        checks["openai"] = "openai_unavailable"
        logger.exception("Deep health check: OpenAI failed")

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthResponse(status=status, checks=checks)
