import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
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
    all_docs = await metadata.get_all_documents(user_id)
    total = len(all_docs)
    start = (page - 1) * ps
    items = all_docs[start : start + ps]
    return PaginatedDocuments(items=items, total=total, page=page, page_size=ps)


@router.get("/documents/{doc_id}/status", response_model=DocumentInfo)
async def document_status(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc or doc.get("user_id") != str(user["_id"]):
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentInfo(**{k: v for k, v in doc.items() if k != "user_id"})


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc or doc.get("user_id") != str(user["_id"]):
        raise HTTPException(status_code=404, detail="Document not found")
    await remove_document(doc_id)
    await metadata.delete_document(doc_id)
    return DeleteResponse(detail="Document deleted")
