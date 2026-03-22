"""Audit log for sensitive actions."""

import logging
from datetime import datetime, timezone

from app.core.database import get_db

logger = logging.getLogger(__name__)


async def log_action(
    action: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    detail: str = "",
    org_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Record an auditable action."""
    db = get_db()
    await db.audit_log.insert_one({
        "action": action,
        "user_id": user_id,
        "org_id": org_id or "",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "detail": detail,
        "ip_address": ip_address or "",
        "created_at": datetime.now(timezone.utc),
    })
    logger.info(
        "audit action=%s user=%s resource=%s/%s",
        action, user_id, resource_type, resource_id,
    )


async def get_audit_log(
    org_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Query audit log with filters."""
    db = get_db()
    query: dict = {}
    if org_id:
        query["org_id"] = org_id
    if user_id:
        query["user_id"] = user_id
    if action:
        query["action"] = action
    if resource_type:
        query["resource_type"] = resource_type

    total = await db.audit_log.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.audit_log.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "action": doc["action"],
            "user_id": doc["user_id"],
            "org_id": doc.get("org_id", ""),
            "resource_type": doc["resource_type"],
            "resource_id": doc["resource_id"],
            "detail": doc.get("detail", ""),
            "ip_address": doc.get("ip_address", ""),
            "created_at": doc["created_at"],
        })
    return items, total
