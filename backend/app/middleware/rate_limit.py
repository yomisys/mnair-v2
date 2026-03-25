"""
Rate limiting middleware for MNAIR API
Implements request rate limits to prevent abuse and ensure fair usage
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from typing import Callable

# Initialize rate limiter
# Uses client IP address as the key for rate limiting
limiter = Limiter(key_func=get_remote_address)


def get_user_identifier(request: Request) -> str:
    """
    Get identifier for rate limiting

    Priority:
    1. User ID from JWT (if authenticated)
    2. IP address (fallback)

    This allows authenticated users to have separate rate limits
    and prevents IP-based rate limit sharing
    """
    # Try to get user from request state (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"

    # Fallback to IP address
    return get_remote_address(request)


# Rate limit configurations for different endpoints
# Format: "requests per time_window"

# General API rate limits (per IP or user)
DEFAULT_RATE_LIMIT = "60/minute"  # 60 requests per minute per user/IP
STRICT_RATE_LIMIT = "10/minute"   # For sensitive endpoints (login, register)
PUBLIC_RATE_LIMIT = "30/minute"   # For public endpoints (certificate verification)

# Authentication endpoints (prevent brute force)
AUTH_RATE_LIMIT = "5/minute"      # 5 login/register attempts per minute

# WhatsApp/USSD webhook endpoints (high volume expected)
WEBHOOK_RATE_LIMIT = "300/minute" # 300 webhook requests per minute

# Quiz submission (prevent spam)
QUIZ_RATE_LIMIT = "10/minute"     # 10 quiz submissions per minute

# Certificate generation (expensive operation)
CERT_RATE_LIMIT = "3/minute"      # 3 certificate generations per minute


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors

    Returns JSON response with rate limit details
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "detail": str(exc.detail) if hasattr(exc, "detail") else None,
        },
        headers=exc.headers if hasattr(exc, "headers") else {},
    )
