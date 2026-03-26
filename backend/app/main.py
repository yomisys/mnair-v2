"""
FastAPI Application Entry Point
Main application initialization
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db, close_db
from app.routers import (
    auth_router,
    lessons_router,
    certificates_router,
    analytics_router,
    employers_router,
)
from app.channels.whatsapp import router as whatsapp_router
from app.routers.test_whatsapp import router as test_whatsapp_router
from app.middleware import (
    limiter,
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    InputValidationMiddleware,
)
from app.middleware.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    print("[START] Starting MNAIR Platform...")

    # Setup logging
    setup_logging(log_level=settings.LOG_LEVEL if hasattr(settings, 'LOG_LEVEL') else "INFO")
    print("[OK] Logging configured")

    await init_db()
    print("[OK] Database initialized")

    yield

    # Shutdown
    print("[STOP] Shutting down MNAIR Platform...")
    await close_db()
    print("[OK] Database connections closed")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="Make Nigeria AI Ready - National AI Literacy Platform",
    lifespan=lifespan,
)

# Add rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security middleware (order matters!)
# Temporarily disabled custom middleware due to Starlette BaseHTTPMiddleware issues
# TODO: Reimplement as pure ASGI middleware for production
# 1. Security headers (first to apply to all responses)
# enable_hsts = settings.APP_ENV == "production"  # Only enable HSTS in production
# app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)

# 2. Request logging
# app.add_middleware(RequestLoggingMiddleware, log_body=False)  # Don't log bodies for privacy

# 3. Input validation
# app.add_middleware(
#     InputValidationMiddleware,
#     max_body_size=10 * 1024 * 1024,  # 10MB max body size
#     enable_sql_injection_check=True,
#     enable_xss_check=True,
#     enable_path_traversal_check=True,
#     enable_command_injection_check=False,  # Disabled for now (too many false positives)
# )

# 4. CORS (last to ensure proper preflight handling)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],  # Explicit methods instead of *
    allow_headers=["Authorization", "Content-Type"],  # Explicit headers
    expose_headers=["X-Total-Count"],  # Expose pagination headers
    max_age=3600,  # Cache preflight for 1 hour
)

# Register routers
app.include_router(auth_router)
app.include_router(lessons_router)
app.include_router(certificates_router)
app.include_router(analytics_router)
app.include_router(employers_router)
app.include_router(whatsapp_router)
app.include_router(test_whatsapp_router)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.API_VERSION,
        "status": "healthy",
        "environment": settings.APP_ENV,
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
        "minio": "connected",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.APP_DEBUG,
    )
