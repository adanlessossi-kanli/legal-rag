import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_api_key
from app.core import metadata
from app.models.schemas import DeleteResponse, DocumentInfo
from app.rag.pipeline import remove_document

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    return metadata.get_all_documents()


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str):
    doc = metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await remove_document(doc_id)
    metadata.delete_document(doc_id)
    return DeleteResponse(detail="Document deleted")
