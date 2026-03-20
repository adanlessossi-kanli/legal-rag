import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pythonjsonlogger import jsonlogger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, chat, conversations, documents, health, upload
from app.core.config import settings
from app.core.database import close_db, connect_db
from app.core.ingestion_queue import start_worker, stop_worker
from app.core.security import SecurityHeadersMiddleware

handler = logging.StreamHandler()
if settings.log_format == "json":
    handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
else:
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await start_worker()

    from app.agents import create_orchestrator
    app.state.orchestrator = await create_orchestrator()

    logger.info("Starting Legal RAG API")
    yield
    await app.state.orchestrator.shutdown()
    await stop_worker()
    await close_db()
    logger.info("Shutting down Legal RAG API")


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Legal RAG API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def request_id_and_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    request.state.request_id = request_id

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s %d %.2fs",
        request.method,
        request.url.path,
        response.status_code,
        duration,
        extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code, "duration": round(duration, 3)},
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, extra={"request_id": request_id})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
