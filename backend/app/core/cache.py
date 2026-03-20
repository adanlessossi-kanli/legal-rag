import hashlib
import json
import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def connect_cache() -> None:
    global _redis
    if not settings.cache_enabled:
        logger.info("Cache disabled")
        return
    try:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        logger.info("Connected to Redis at %s", settings.redis_url)
    except Exception:
        logger.warning("Redis unavailable — caching disabled", exc_info=True)
        _redis = None


async def close_cache() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


async def _user_gen(user_id: str) -> str:
    """Get the current cache generation for a user (changes on doc upload/delete)."""
    gen = await _redis.get(f"cache_gen:{user_id}")  # type: ignore[union-attr]
    return gen or "0"


def _cache_key(user_id: str, gen: str, question: str, document_ids: list[str] | None) -> str:
    doc_part = ",".join(sorted(document_ids)) if document_ids else ""
    raw = f"{user_id}:{gen}:{question.strip().lower()}:{doc_part}"
    return f"chat:{hashlib.sha256(raw.encode()).hexdigest()}"


async def get_cached_response(user_id: str, question: str, document_ids: list[str] | None) -> dict | None:
    if not _redis:
        return None
    try:
        gen = await _user_gen(user_id)
        data = await _redis.get(_cache_key(user_id, gen, question, document_ids))
        if data:
            logger.debug("Cache hit for user %s", user_id)
            return json.loads(data)
        return None
    except Exception:
        logger.warning("Cache read failed", exc_info=True)
        return None


async def set_cached_response(
    user_id: str, question: str, document_ids: list[str] | None, response: dict,
) -> None:
    if not _redis:
        return
    try:
        gen = await _user_gen(user_id)
        key = _cache_key(user_id, gen, question, document_ids)
        await _redis.set(key, json.dumps(response), ex=settings.cache_ttl_seconds)
    except Exception:
        logger.warning("Cache write failed", exc_info=True)


async def invalidate_user_cache(user_id: str) -> None:
    """Bump generation counter — all old cache keys become unreachable."""
    if not _redis:
        return
    try:
        await _redis.incr(f"cache_gen:{user_id}")
    except Exception:
        logger.warning("Cache invalidation failed", exc_info=True)
