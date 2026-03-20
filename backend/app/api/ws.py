import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings
from app.core.notifications import ingestion_notifier

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_user_id(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/ingestion")
async def ingestion_ws(ws: WebSocket):
    # Auth via query param: ?token=<jwt>
    token = ws.query_params.get("token", "")
    user_id = _extract_user_id(token)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ingestion_notifier.connect(user_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive; client can send pings
    except WebSocketDisconnect:
        pass
    finally:
        ingestion_notifier.disconnect(user_id, ws)
