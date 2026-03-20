import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class IngestionNotifier:
    """Manages per-user WebSocket connections for ingestion status updates."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[user_id].append(ws)

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(user_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(user_id, None)

    async def notify(self, user_id: str, doc_id: str, status: str, name: str = "", chunk_count: int = 0, error: str | None = None) -> None:
        payload = json.dumps({
            "type": "ingestion_status",
            "doc_id": doc_id,
            "status": status,
            "name": name,
            "chunk_count": chunk_count,
            "error": error,
        })
        dead: list[WebSocket] = []
        for ws in self._connections.get(user_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


ingestion_notifier = IngestionNotifier()
