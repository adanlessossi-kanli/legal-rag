import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user, get_org_id
from app.core.cache import invalidate_user_cache
from app.core.config import settings
from app.core import metadata
from app.models.schemas import DeleteResponse, DocumentInfo, PaginatedDocuments
from app.rag.pipeline import remove_document

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/documents", response_model=PaginatedDocuments)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    user: dict = Depends(get_current_user),
):
    ps = min(page_size or settings.default_page_size, settings.max_page_size)
    user_id = str(user["_id"])
    org_id = get_org_id(user)
    items, total = await metadata.get_documents_paginated(user_id, org_id, page, ps)
    return PaginatedDocuments(items=items, total=total, page=page, page_size=ps)


@router.get("/documents/{doc_id}/status", response_model=DocumentInfo)
async def document_status(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Allow access if user owns doc or belongs to same org
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentInfo(**{k: v for k, v in doc.items() if k not in ("user_id", "org_id")})


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Allow delete if user owns doc or is in same org
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=404, detail="Document not found")
    await remove_document(doc_id)
    await metadata.delete_document(doc_id)
    await invalidate_user_cache(str(user["_id"]))
    return DeleteResponse(detail="Document deleted")
