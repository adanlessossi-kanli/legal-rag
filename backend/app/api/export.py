import json
import logging
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.auth import get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


def _safe_oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid ID format")


def _format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else ""


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    convo = await db.conversations.find_one({"_id": _safe_oid(conversation_id), "user_id": user["_id"]})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor = db.messages.find({"conversation_id": convo["_id"]}).sort("created_at", 1)
    messages = []
    async for m in cursor:
        messages.append({
            "role": m["role"],
            "content": m["content"],
            "sources": m.get("sources", []),
            "created_at": m["created_at"],
        })

    title = convo.get("title", "Conversation")

    if format == "json":
        export_data = {
            "title": title,
            "exported_at": datetime.utcnow().isoformat(),
            "messages": [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "sources": m["sources"],
                    "timestamp": m["created_at"].isoformat() if m["created_at"] else None,
                }
                for m in messages
            ],
        }
        return Response(
            content=json.dumps(export_data, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{title[:50]}.json"'},
        )

    # Markdown format
    lines = [f"# {title}\n"]
    for m in messages:
        role_label = "**You**" if m["role"] == "user" else "**Assistant**"
        timestamp = _format_datetime(m["created_at"])
        lines.append(f"### {role_label} — {timestamp}\n")
        lines.append(m["content"])
        if m["sources"]:
            lines.append("\n**Sources:**")
            for s in m["sources"]:
                doc_name = s.get("document", "unknown")
                text = s.get("text", "")[:150]
                lines.append(f"- *{doc_name}*: {text}")
        lines.append("\n---\n")

    content = "\n".join(lines)
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{title[:50]}.md"'},
    )
