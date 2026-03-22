import logging
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import (
    CreateOrgRequest,
    InviteMemberRequest,
    OrgDetail,
    OrgMember,
    OrgSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/organizations", dependencies=[Depends(get_current_user)])


def _safe_oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid ID format")


@router.post("", response_model=OrgDetail, status_code=201)
async def create_org(req: CreateOrgRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    now = datetime.now(timezone.utc)
    user_id = user["_id"]

    result = await db.organizations.insert_one({
        "name": req.name,
        "owner_id": user_id,
        "created_at": now,
    })
    org_id = result.inserted_id

    # Add owner as admin member
    await db.org_members.insert_one({
        "org_id": org_id,
        "user_id": user_id,
        "role": "admin",
        "joined_at": now,
    })

    # Set org on user if they don't have one
    if not user.get("org_id"):
        await db.users.update_one({"_id": user_id}, {"$set": {"org_id": org_id}})

    return OrgDetail(
        id=str(org_id),
        name=req.name,
        owner_id=str(user_id),
        created_at=now,
        members=[OrgMember(user_id=str(user_id), email=user["email"], name=user["name"], role="admin")],
    )


@router.get("", response_model=list[OrgSummary])
async def list_orgs(user: dict = Depends(get_current_user)):
    db = get_db()
    memberships = db.org_members.find({"user_id": user["_id"]})
    org_ids = [m["org_id"] async for m in memberships]
    if not org_ids:
        return []
    orgs = []
    async for org in db.organizations.find({"_id": {"$in": org_ids}}):
        count = await db.org_members.count_documents({"org_id": org["_id"]})
        orgs.append(OrgSummary(id=str(org["_id"]), name=org["name"], member_count=count))
    return orgs


@router.get("/{org_id}", response_model=OrgDetail)
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = _safe_oid(org_id)
    membership = await db.org_members.find_one({"org_id": oid, "user_id": user["_id"]})
    if not membership:
        raise HTTPException(status_code=404, detail="Organization not found")

    org = await db.organizations.find_one({"_id": oid})
    members = []
    async for m in db.org_members.find({"org_id": oid}):
        u = await db.users.find_one({"_id": m["user_id"]})
        if u:
            members.append(OrgMember(user_id=str(u["_id"]), email=u["email"], name=u["name"], role=m["role"]))

    return OrgDetail(
        id=str(org["_id"]),
        name=org["name"],
        owner_id=str(org["owner_id"]),
        created_at=org["created_at"],
        members=members,
    )


@router.post("/{org_id}/members", response_model=OrgMember, status_code=201)
async def invite_member(org_id: str, req: InviteMemberRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = _safe_oid(org_id)

    # Only admins can invite
    membership = await db.org_members.find_one({"org_id": oid, "user_id": user["_id"]})
    if not membership or membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can invite members")

    target = await db.users.find_one({"email": req.email.lower()})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.org_members.find_one({"org_id": oid, "user_id": target["_id"]})
    if existing:
        raise HTTPException(status_code=409, detail="User already a member")

    now = datetime.now(timezone.utc)
    await db.org_members.insert_one({
        "org_id": oid,
        "user_id": target["_id"],
        "role": req.role,
        "joined_at": now,
    })
    await db.users.update_one({"_id": target["_id"]}, {"$set": {"org_id": oid}})

    return OrgMember(user_id=str(target["_id"]), email=target["email"], name=target["name"], role=req.role)


@router.delete("/{org_id}/members/{user_id}")
async def remove_member(org_id: str, user_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = _safe_oid(org_id)

    membership = await db.org_members.find_one({"org_id": oid, "user_id": user["_id"]})
    if not membership or membership["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can remove members")

    org = await db.organizations.find_one({"_id": oid})
    if str(org["owner_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the owner")

    target_oid = _safe_oid(user_id)
    result = await db.org_members.delete_one({"org_id": oid, "user_id": target_oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.users.update_one({"_id": target_oid}, {"$unset": {"org_id": ""}})
    return {"detail": "Member removed"}
