import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(_header)) -> None:
    if not settings.api_key:
        return
    if key is None or not hmac.compare_digest(key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
