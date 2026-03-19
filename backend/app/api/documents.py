import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core import metadata
from app.models.schemas import DeleteResponse, DocumentInfo
from app.rag.pipeline import remove_document

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(user: dict = Depends(get_current_user)):
    return await metadata.get_all_documents(str(user["_id"]))


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await metadata.get_document(doc_id)
    if not doc or doc.get("user_id") != str(user["_id"]):
        raise HTTPException(status_code=404, detail="Document not found")
    await remove_document(doc_id)
    await metadata.delete_document(doc_id)
    return DeleteResponse(detail="Document deleted")
