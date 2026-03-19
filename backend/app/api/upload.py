import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import verify_api_key
from app.core.config import settings
from app.core.metadata import find_by_hash, save_document, update_status
from app.models.schemas import UploadResponse
from app.rag.pipeline import compute_hash, ingest

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_api_key)])
limiter = Limiter(key_func=get_remote_address)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}
MAX_SIZE_BYTES = 50 * 1024 * 1024


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)


async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while chunk := await file.read(65_536):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="File exceeds 50MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def _background_ingest(file_path: str, original_name: str, doc_id: str, content_hash: str) -> None:
    try:
        await ingest(file_path, original_name, doc_id, content_hash)
    except Exception:
        logger.exception("Background ingestion failed for %s", doc_id)
        update_status(doc_id, "error")


@router.post("/upload", response_model=UploadResponse)
@limiter.limit(settings.rate_limit_upload)
async def upload(request: Request, file: UploadFile, background_tasks: BackgroundTasks):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    content = await _read_with_limit(file, MAX_SIZE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    content_hash = compute_hash(content)
    existing = find_by_hash(content_hash)
    if existing:
        raise HTTPException(status_code=409, detail=f"Document already uploaded as '{existing['name']}' (id: {existing['id']})")

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    safe_name = _sanitize_filename(file.filename)
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}_{safe_name}"
    file_path.write_bytes(content)

    # Save initial metadata and kick off background ingestion
    save_document(doc_id, file.filename, 0, "processing", content_hash)
    background_tasks.add_task(_background_ingest, str(file_path), file.filename, doc_id, content_hash)

    return UploadResponse(id=doc_id, name=file.filename, chunk_count=0, status="processing")
