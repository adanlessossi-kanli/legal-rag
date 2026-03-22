import logging
from collections import defaultdict
from datetime import datetime, timezone
from time import time
from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Account lockout (in-memory, resets on restart) ---

_login_attempts: dict[str, list[float]] = defaultdict(list)


def record_failed_login(email: str) -> None:
    now = time()
    _login_attempts[email].append(now)


def clear_login_attempts(email: str) -> None:
    _login_attempts.pop(email, None)


def is_account_locked(email: str) -> bool:
    cutoff = time() - (settings.lockout_duration_minutes * 60)
    attempts = [t for t in _login_attempts.get(email, []) if t > cutoff]
    _login_attempts[email] = attempts
    return len(attempts) >= settings.max_login_attempts


# --- CSP middleware ---

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if settings.enable_csp:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self' https://api.openai.com"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not (request.url.path.endswith("/file") and "/documents/" in request.url.path):
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# --- CSRF protection ---

class CSRFMiddleware(BaseHTTPMiddleware):
    """Origin-based CSRF protection for state-changing requests.

    Validates that the Origin or Referer header matches trusted origins
    for POST/PUT/DELETE requests. API clients using Bearer tokens are
    exempt since CSRF only affects cookie-based auth.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.enable_csrf_protection:
            return await call_next(request)

        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Bearer token requests are not vulnerable to CSRF
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # Check Origin header
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        trusted = set(settings.csrf_trusted_origins.split(","))

        if origin:
            if origin not in trusted:
                logger.warning("CSRF: rejected origin %s", origin)
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        elif referer:
            ref_origin = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
            if ref_origin not in trusted:
                logger.warning("CSRF: rejected referer %s", referer)
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

        return await call_next(request)
