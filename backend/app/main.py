"""
FastAPI Application Entry Point
Main application initialization
"""

import time
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.database import init_db, close_db, get_db
from app.routers import (
    auth_router,
    lessons_router,
    certificates_router,
    analytics_router,
    employers_router,
)
from app.channels.telegram import router as telegram_router
from app.channels.web import router as learn_router
from app.middleware import limiter
from app.middleware.logging import setup_logging

logger = logging.getLogger(__name__)

# ── SQL injection / XSS / path-traversal patterns (compiled once at startup) ──
_SQL_PATTERNS = [
    re.compile(r"(\bUNION\b.*\bSELECT\b)", re.IGNORECASE),
    re.compile(r"(\bSELECT\b.*\bFROM\b.*\bWHERE\b)", re.IGNORECASE),
    re.compile(r"(\bINSERT\b.*\bINTO\b)", re.IGNORECASE),
    re.compile(r"(\bUPDATE\b.*\bSET\b)", re.IGNORECASE),
    re.compile(r"(\bDELETE\b.*\bFROM\b)", re.IGNORECASE),
    re.compile(r"(\bDROP\b.*\bTABLE\b)", re.IGNORECASE),
    re.compile(r"(;.*--)"),
    re.compile(r"('.*OR.*'.*=.*')"),
]
_XSS_PATTERNS = [
    re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"<iframe", re.IGNORECASE),
]
_PATH_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"%2e%2e", re.IGNORECASE),
]

_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(log_level="INFO")
    logger.info("Starting MNAIR Platform...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down MNAIR Platform...")
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="Make Nigeria AI Ready - National AI Literacy Platform",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Middleware (registration order is LIFO → last registered runs first) ──
# Desired request order: CORS → InputValidation → RequestLogging → SecurityHeaders → handler
# Register in reverse: SecurityHeaders first, then Logging, then Validation, then CORS last.

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/docs") or request.url.path == "/openapi.json":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
            "font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"
        )
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "Request started",
        extra={"method": method, "path": path, "client_ip": client_ip},
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Request failed",
            extra={"method": method, "path": path, "error": str(exc)},
        )
        raise
    duration = time.time() - start
    logger.info(
        "Request completed",
        extra={
            "method": method,
            "path": path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000),
        },
    )
    return response


@app.middleware("http")
async def validate_input(request: Request, call_next):
    # Skip validation for OPTIONS preflight (handled by CORS before this runs)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Check content-length before reading
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large (max 10MB)"},
        )

    # Read and cache the body so downstream handlers can read it too.
    # Calling request.body() caches it in request._body automatically
    # (FastAPI 0.109 / Starlette 0.36 behaviour — verified).
    body = await request.body()
    if len(body) > _MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large (max 10MB)"},
        )

    if body:
        body_text = body.decode("utf-8", errors="ignore")
        for pattern in _SQL_PATTERNS:
            if pattern.search(body_text):
                logger.warning("SQL injection pattern detected", extra={"path": request.url.path, "client_ip": request.client.host if request.client else "unknown"})
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})
        for pattern in _XSS_PATTERNS:
            if pattern.search(body_text):
                logger.warning("XSS pattern detected", extra={"path": request.url.path})
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})
        for pattern in _PATH_PATTERNS:
            if pattern.search(request.url.path):
                logger.warning("Path traversal attempt", extra={"path": request.url.path})
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})

    return await call_next(request)


# CORS — registered last so it wraps everything (runs first for requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Total-Count"],
    max_age=3600,
)


# ── Routers ──
app.include_router(auth_router)
app.include_router(lessons_router)
app.include_router(certificates_router)
app.include_router(analytics_router)
app.include_router(employers_router)
# Free learner channels (replaced the WhatsApp webhook — see app/engine)
app.include_router(telegram_router)
app.include_router(learn_router)


# ── Routes ──
@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.API_VERSION,
        "status": "healthy",
        "environment": settings.APP_ENV,
        "channels": {
            "telegram": bool(settings.TELEGRAM_BOT_TOKEN),
            "web": True,
            "webpush": settings.webpush_configured,
            "ussd": True,
            "sms_reminders": settings.SMS_REMINDERS_ENABLED,
        },
    }


@app.get("/health")
async def health_check():
    """Real connectivity health check — returns 503 if any service is down."""
    from app.database import engine
    import redis.asyncio as aioredis

    checks = {}
    overall = True

    # PostgreSQL
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as exc:
        logger.error("Health check: database unreachable", extra={"error": str(exc)})
        checks["database"] = "unreachable"
        overall = False

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as exc:
        logger.error("Health check: redis unreachable", extra={"error": str(exc)})
        checks["redis"] = "unreachable"
        overall = False

    # MinIO / S3
    try:
        from minio import Minio
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        client.bucket_exists(settings.MINIO_BUCKET)
        checks["minio"] = "connected"
    except Exception as exc:
        logger.error("Health check: minio unreachable", extra={"error": str(exc)})
        checks["minio"] = "unreachable"
        overall = False

    status_code = 200 if overall else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if overall else "degraded", **checks},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.APP_DEBUG)
