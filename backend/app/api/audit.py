import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.audit import get_audit_log
from app.core.auth import get_current_user, get_org_id
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import AuditLogEntry, PaginatedAuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", dependencies=[Depends(get_current_user)])


@router.get("", response_model=PaginatedAuditLog)
async def list_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if not settings.enable_audit_log:
        raise HTTPException(status_code=404, detail="Audit log is disabled")

    org_id = get_org_id(user)

    # Only org admins can view the full org audit log
    if org_id:
        db = get_db()
        membership = await db.org_members.find_one({"org_id": user.get("org_id"), "user_id": user["_id"]})
        if not membership or membership["role"] != "admin":
            # Non-admins can only see their own actions
            items, total = await get_audit_log(
                user_id=str(user["_id"]), action=action,
                resource_type=resource_type, page=page, page_size=page_size,
            )
        else:
            items, total = await get_audit_log(
                org_id=org_id, action=action,
                resource_type=resource_type, page=page, page_size=page_size,
            )
    else:
        items, total = await get_audit_log(
            user_id=str(user["_id"]), action=action,
            resource_type=resource_type, page=page, page_size=page_size,
        )

    return PaginatedAuditLog(items=items, total=total, page=page, page_size=page_size)
