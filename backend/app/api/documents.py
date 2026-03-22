import hashlib
import hmac
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

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
    file_type: str | None = Query(None, pattern="^(pdf|txt|docx|pptx)$"),
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


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _sign_url(doc_id: str, user_id: str) -> tuple[str, int]:
    exp = int(time.time()) + settings.file_token_expiry_seconds
    msg = f"{doc_id}:{user_id}:{exp}"
    sig = hmac.new(settings.jwt_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return sig, exp


def _verify_sig(doc_id: str, user_id: str, sig: str, exp: int) -> bool:
    if int(time.time()) > exp:
        return False
    msg = f"{doc_id}:{user_id}:{exp}"
    expected = hmac.new(settings.jwt_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


async def _get_doc_and_verify(doc_id: str, user: dict) -> dict:
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    org_id = get_org_id(user)
    if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return doc


def _find_file(doc_id: str) -> Path | None:
    upload_dir = Path(settings.upload_dir).resolve()
    if not upload_dir.exists():
        return None
    for f in upload_dir.iterdir():
        if f.name.startswith(doc_id):
            resolved = f.resolve()
            if str(resolved).startswith(str(upload_dir)):
                return resolved
    return None


@router.get("/documents/{doc_id}/file-token")
async def file_token(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await _get_doc_and_verify(doc_id, user)
    sig, exp = _sign_url(doc_id, doc.get("user_id", str(user["_id"])))
    return {"url": f"/api/documents/{doc_id}/file?sig={sig}&exp={exp}"}


@router.get("/documents/{doc_id}/file")
async def serve_file(
    doc_id: str,
    request: Request,
    sig: str | None = Query(None),
    exp: int | None = Query(None),
    user: dict | None = Depends(get_current_user),
):
    doc = await metadata.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Auth: signed URL or Bearer token
    if sig and exp:
        if not _verify_sig(doc_id, doc.get("user_id", ""), sig, exp):
            raise HTTPException(status_code=403, detail="Invalid or expired signature")
    elif user:
        org_id = get_org_id(user)
        if doc.get("user_id") != str(user["_id"]) and (not org_id or doc.get("org_id") != org_id):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")

    file_path = _find_file(doc_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available on disk")

    ext = file_path.suffix.lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    content_hash = doc.get("content_hash", "")

    # ETag / If-None-Match
    if_none_match = request.headers.get("if-none-match")
    if content_hash and if_none_match and if_none_match.strip('"') == content_hash:
        return Response(status_code=304)

    headers = {
        "Content-Disposition": f'inline; filename="{doc.get("name", file_path.name)}"',
        "Cache-Control": "private, max-age=3600, immutable",
        "Accept-Ranges": "bytes",
    }
    if content_hash:
        headers["ETag"] = f'"{content_hash}"'

    # Range request support
    range_header = request.headers.get("range")
    if range_header:
        file_size = file_path.stat().st_size
        try:
            range_spec = range_header.replace("bytes=", "")
            start_str, end_str = range_spec.split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1
            with open(file_path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(length)
            return Response(content=data, status_code=206, media_type=content_type, headers=headers)
        except (ValueError, IndexError):
            pass

    return FileResponse(path=str(file_path), media_type=content_type, headers=headers)
