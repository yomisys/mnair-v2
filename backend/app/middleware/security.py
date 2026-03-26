"""
Security headers middleware for MNAIR API
Adds security headers to all responses to protect against common attacks
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Enables XSS filter in older browsers
    - Strict-Transport-Security: Enforces HTTPS (if enabled)
    - Content-Security-Policy: Controls resource loading
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    """

    def __init__(self, app, enable_hsts: bool = False):
        """
        Initialize security headers middleware

        Args:
            app: FastAPI application
            enable_hsts: Whether to enable HSTS (only for production HTTPS)
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response"""
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking - only allow same origin
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Enable XSS filter in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS - enforce HTTPS (only in production with SSL)
        if self.enable_hsts:
            # max-age=31536000 (1 year), includeSubDomains
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Content Security Policy
        # Restricts resource loading to prevent XSS attacks
        csp_directives = [
            "default-src 'self'",                    # Default to same origin
            "script-src 'self' 'unsafe-inline'",     # Allow inline scripts (for docs)
            "style-src 'self' 'unsafe-inline'",      # Allow inline styles (for docs)
            "img-src 'self' data: https:",           # Allow images from same origin, data URLs, and HTTPS
            "font-src 'self' data:",                 # Allow fonts from same origin and data URLs
            "connect-src 'self'",                    # API calls to same origin only
            "frame-ancestors 'self'",                # Only allow framing by same origin
            "base-uri 'self'",                       # Restrict base tag URLs
            "form-action 'self'",                    # Restrict form submissions
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Referrer Policy - control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature Policy)
        # Disable unnecessary browser features
        permissions_directives = [
            "accelerometer=()",      # Disable accelerometer
            "camera=()",             # Disable camera
            "geolocation=()",        # Disable geolocation
            "gyroscope=()",          # Disable gyroscope
            "magnetometer=()",       # Disable magnetometer
            "microphone=()",         # Disable microphone
            "payment=()",            # Disable payment API
            "usb=()",                # Disable USB
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions_directives)

        # Remove server header to avoid information disclosure
        if "Server" in response.headers: del response.headers["Server"]

        return response
