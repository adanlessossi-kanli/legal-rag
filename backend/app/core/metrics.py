import re
import time

from fastapi import Request
from prometheus_client import Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Normalize paths to prevent label cardinality explosion
_PATH_PATTERNS = [
    (re.compile(r"/api/documents/[^/]+/status"), "/api/documents/{id}/status"),
    (re.compile(r"/api/documents/[^/]+/versions"), "/api/documents/{id}/versions"),
    (re.compile(r"/api/documents/[^/]+"), "/api/documents/{id}"),
    (re.compile(r"/api/conversations/[^/]+/export"), "/api/conversations/{id}/export"),
    (re.compile(r"/api/conversations/[^/]+"), "/api/conversations/{id}"),
    (re.compile(r"/api/organizations/[^/]+/members/[^/]+/role"), "/api/organizations/{id}/members/{uid}/role"),
    (re.compile(r"/api/organizations/[^/]+/members/[^/]+"), "/api/organizations/{id}/members/{uid}"),
    (re.compile(r"/api/organizations/[^/]+/members"), "/api/organizations/{id}/members"),
    (re.compile(r"/api/organizations/[^/]+"), "/api/organizations/{id}"),
    (re.compile(r"/api/blueprints/[^/]+"), "/api/blueprints/{id}"),
]


def _normalize_path(path: str) -> str:
    for pattern, replacement in _PATH_PATTERNS:
        if pattern.fullmatch(path):
            return replacement
    return path

# --- HTTP metrics ---

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path", "status"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP errors (4xx/5xx)",
    ["method", "path", "status"],
)

# --- OpenAI metrics ---

LLM_LATENCY = Histogram(
    "openai_request_duration_seconds",
    "OpenAI API call latency",
    ["operation"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

LLM_TOKENS = Counter(
    "openai_tokens_total",
    "Total OpenAI tokens used",
    ["type"],  # prompt, completion
)

LLM_ERRORS = Counter(
    "openai_errors_total",
    "Total OpenAI API errors",
    ["operation"],
)

# --- Retrieval metrics ---

RETRIEVAL_LATENCY = Histogram(
    "retrieval_duration_seconds",
    "Vector search retrieval latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

RETRIEVAL_CHUNKS = Histogram(
    "retrieval_chunks_returned",
    "Number of chunks returned per retrieval",
    buckets=[0, 1, 2, 3, 5, 10, 20],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/api/metrics":
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        path = _normalize_path(request.url.path)
        method = request.method
        status = str(response.status_code)

        REQUEST_LATENCY.labels(method, path, status).observe(duration)
        REQUEST_COUNT.labels(method, path, status).inc()

        if response.status_code >= 400:
            ERROR_COUNT.labels(method, path, status).inc()

        return response


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")
