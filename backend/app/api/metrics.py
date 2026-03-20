from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.core.metrics import metrics_response
from app.core.usage import get_user_usage

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return metrics_response()


@router.get("/usage")
async def usage(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    user: dict = Depends(get_current_user),
):
    return await get_user_usage(str(user["_id"]), month)
