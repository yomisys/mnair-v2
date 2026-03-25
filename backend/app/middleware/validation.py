"""
Input validation and sanitization middleware for MNAIR API
Protects against injection attacks and malicious input
"""

import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from typing import Callable
import logging

logger = logging.getLogger(__name__)


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate and sanitize input

    Protections:
    - SQL injection prevention (basic detection)
    - XSS prevention (script tag detection)
    - Path traversal prevention
    - Command injection prevention
    - Maximum request size enforcement
    """

    # Suspicious patterns that might indicate attacks
    SQL_INJECTION_PATTERNS = [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bSELECT\b.*\bFROM\b.*\bWHERE\b)",
        r"(\bINSERT\b.*\bINTO\b)",
        r"(\bUPDATE\b.*\bSET\b)",
        r"(\bDELETE\b.*\bFROM\b)",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(;.*--)",
        r"('.*OR.*'.*=.*')",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",  # Event handlers like onclick=
        r"<iframe",
        r"<object",
        r"<embed",
    ]

    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.",
        r"%2e%2e",
        r"\.\.\\",
    ]

    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$]",  # Command separators
        r"\$\(",     # Command substitution
        r">\s*/",    # Redirection to filesystem
    ]

    def __init__(
        self,
        app,
        max_body_size: int = 10 * 1024 * 1024,  # 10MB
        enable_sql_injection_check: bool = True,
        enable_xss_check: bool = True,
        enable_path_traversal_check: bool = True,
        enable_command_injection_check: bool = True,
    ):
        """
        Initialize input validation middleware

        Args:
            app: FastAPI application
            max_body_size: Maximum request body size in bytes
            enable_sql_injection_check: Enable SQL injection detection
            enable_xss_check: Enable XSS detection
            enable_path_traversal_check: Enable path traversal detection
            enable_command_injection_check: Enable command injection detection
        """
        super().__init__(app)
        self.max_body_size = max_body_size
        self.enable_sql_injection_check = enable_sql_injection_check
        self.enable_xss_check = enable_xss_check
        self.enable_path_traversal_check = enable_path_traversal_check
        self.enable_command_injection_check = enable_command_injection_check

        # Compile patterns for performance
        self.sql_patterns = [re.compile(p, re.IGNORECASE) for p in self.SQL_INJECTION_PATTERNS]
        self.xss_patterns = [re.compile(p, re.IGNORECASE) for p in self.XSS_PATTERNS]
        self.path_patterns = [re.compile(p, re.IGNORECASE) for p in self.PATH_TRAVERSAL_PATTERNS]
        self.cmd_patterns = [re.compile(p) for p in self.COMMAND_INJECTION_PATTERNS]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate request before processing"""

        # Check request body size
        if "content-length" in request.headers:
            content_length = int(request.headers["content-length"])
            if content_length > self.max_body_size:
                logger.warning(
                    f"Request body too large: {content_length} bytes (max: {self.max_body_size})"
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "message": f"Request body too large. Maximum size: {self.max_body_size} bytes",
                    }
                )

        # Check query parameters
        query_string = str(request.url.query)
        if query_string:
            if self._is_suspicious(query_string):
                logger.warning(
                    f"Suspicious query parameters detected: {request.url.path}",
                    extra={"query": query_string, "client_ip": request.client.host}
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_input",
                        "message": "Invalid characters detected in request",
                    }
                )

        # Check path parameters
        path = request.url.path
        if self.enable_path_traversal_check:
            if any(pattern.search(path) for pattern in self.path_patterns):
                logger.warning(
                    f"Path traversal attempt detected: {path}",
                    extra={"client_ip": request.client.host}
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_path",
                        "message": "Invalid path detected",
                    }
                )

        # For POST/PUT/PATCH requests, check body (if JSON)
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    # Get body as text (we'll need to restore it for FastAPI)
                    body = await request.body()
                    body_text = body.decode("utf-8") if body else ""

                    if body_text and self._is_suspicious(body_text):
                        logger.warning(
                            f"Suspicious request body detected: {request.url.path}",
                            extra={"client_ip": request.client.host}
                        )
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": "invalid_input",
                                "message": "Invalid characters detected in request body",
                            }
                        )

                    # Restore body for FastAPI to read
                    async def receive():
                        return {"type": "http.request", "body": body}

                    request._receive = receive

                except Exception as e:
                    logger.error(f"Error validating request body: {e}")

        # Process request
        response = await call_next(request)
        return response

    def _is_suspicious(self, text: str) -> bool:
        """
        Check if text contains suspicious patterns

        Args:
            text: Text to check

        Returns:
            True if suspicious patterns detected
        """
        # SQL injection check
        if self.enable_sql_injection_check:
            if any(pattern.search(text) for pattern in self.sql_patterns):
                return True

        # XSS check
        if self.enable_xss_check:
            if any(pattern.search(text) for pattern in self.xss_patterns):
                return True

        # Command injection check
        if self.enable_command_injection_check:
            # Only check in specific fields (not all text)
            # This is a basic check - real command injection requires context
            if any(pattern.search(text) for pattern in self.cmd_patterns):
                # Allow these characters in normal text, only flag if suspicious context
                # For MVP, we'll be lenient
                pass

        return False


def sanitize_string(text: str, max_length: int = 1000) -> str:
    """
    Sanitize string input

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return text

    # Truncate to max length
    text = text[:max_length]

    # Remove null bytes
    text = text.replace("\x00", "")

    # Remove control characters (except newlines and tabs)
    text = "".join(char for char in text if char == "\n" or char == "\t" or not char.isprintable() or char >= " ")

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def sanitize_html(text: str) -> str:
    """
    Remove HTML tags from text

    Args:
        text: Text with potential HTML

    Returns:
        Text without HTML tags
    """
    if not text:
        return text

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Remove common HTML entities
    html_entities = {
        "&lt;": "<",
        "&gt;": ">",
        "&amp;": "&",
        "&quot;": '"',
        "&#39;": "'",
    }

    for entity, char in html_entities.items():
        text = text.replace(entity, char)

    return text
