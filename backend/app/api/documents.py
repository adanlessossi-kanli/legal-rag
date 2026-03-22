import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user, get_org_id
from app.core.cache import invalidate_user_cache
from app.core.config import settings
from app.core import metadata
from app.core.audit import log_action
from app.models.schemas import DeleteResponse, DocumentInfo, DocumentVersion, PaginatedDocuments
from app.rag.pipeline import remove_document

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/documents", response_model=PaginatedDocuments)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    search: str | None = Query(None, max_length=200),
    status: str | None = Query(None, pattern="^(processing|ready|error)$"),
    file_type: str | None = Query(None, pattern="^(pdf|txt|docx)$"),
    sort_by: str = Query("uploaded_at", pattern="^(name|uploaded_at|chunk_count)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    user: dict = Depends(get_current_user),
):
    ps = min(page_size or settings.default_page_size, settings.max_page_size)
    user_id = str(user["_id"])
    org_id = get_org_id(user)
    items, total = await metadata.get_documents_paginated(
        user_id, org_id, page, ps,
        search=search, status_filter=status, file_type=file_type,
        sort_by=sort_by, sort_order=sort_order,
    )
    return PaginatedDocuments(items=items, total=total, page=page, page_size=ps)


@router.get("/documents/{doc_id}/status", response_model=DocumentInfo)
async def document_status(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentInfo(**{k: v for k, v in doc.items() if k not in ("user_id", "org_id")})


@router.get("/documents/{doc_id}/versions", response_model=list[DocumentVersion])
async def document_versions(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return await metadata.get_document_versions(doc_id)


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=404, detail="Document not found")
    await remove_document(doc_id)
    await metadata.delete_document(doc_id)
    await invalidate_user_cache(str(user["_id"]))

    if settings.enable_audit_log:
        await log_action(
            action="document.delete",
            user_id=str(user["_id"]),
            resource_type="document",
            resource_id=doc_id,
            detail=f"Deleted document: {doc.get('name', '')}",
            org_id=org_id,
        )

    return DeleteResponse(detail="Document deleted")
