import logging
from collections import defaultdict
from datetime import datetime, timezone
from time import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

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
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
