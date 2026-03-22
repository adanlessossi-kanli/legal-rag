import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import get_current_user, get_org_id
from app.core.cache import invalidate_user_cache
from app.core.config import settings
from app.core.ingestion_queue import enqueue
from app.core.metadata import find_by_hash, save_document
from app.models.schemas import UploadResponse
from app.rag.pipeline import compute_hash

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])
limiter = Limiter(key_func=get_remote_address)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".pptx"}
MAX_SIZE_BYTES = 50 * 1024 * 1024


def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.\-]", "_", name)
    # Collapse consecutive dots to prevent path traversal
    name = re.sub(r"\.{2,}", "_", name)
    return name


async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while chunk := await file.read(65_536):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="File exceeds 50MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/upload", response_model=UploadResponse)
@limiter.limit(settings.rate_limit_upload)
async def upload(request: Request, file: UploadFile, user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    content = await _read_with_limit(file, MAX_SIZE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    user_id = str(user["_id"])
    org_id = get_org_id(user) or ""
    content_hash = compute_hash(content)
    existing = await find_by_hash(content_hash, user_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Document already uploaded as '{existing['name']}' (id: {existing['id']})")

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    safe_name = _sanitize_filename(file.filename)
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}_{safe_name}"
    file_path.write_bytes(content)

    await save_document(doc_id, file.filename, 0, "processing", content_hash, user_id, org_id)
    await enqueue(str(file_path), file.filename, doc_id, content_hash, user_id, org_id)
    await invalidate_user_cache(user_id)

    return UploadResponse(id=doc_id, name=file.filename, chunk_count=0, status="processing")
