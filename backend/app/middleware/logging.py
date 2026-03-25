"""
Request logging middleware for MNAIR API
Logs all API requests for monitoring and debugging
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests and responses

    Logs:
    - Request method and path
    - Request duration
    - Response status code
    - User ID (if authenticated)
    - Client IP address
    - User agent
    """

    def __init__(self, app, log_body: bool = False):
        """
        Initialize request logging middleware

        Args:
            app: FastAPI application
            log_body: Whether to log request/response bodies (disabled by default for privacy)
        """
        super().__init__(app)
        self.log_body = log_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details"""
        start_time = time.time()

        # Extract request details
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Get user ID if authenticated
        user_id = None
        if hasattr(request.state, "user") and request.state.user:
            user_id = request.state.user.id

        # Log request
        logger.info(
            f"Request started: {method} {path}",
            extra={
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "user_id": user_id,
                "user_agent": user_agent,
            }
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log exception
            duration = time.time() - start_time
            logger.error(
                f"Request failed: {method} {path} - {str(e)} ({duration:.2f}s)",
                extra={
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "user_id": user_id,
                    "duration": duration,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        status_code = response.status_code
        log_level = logging.INFO if status_code < 400 else logging.WARNING

        logger.log(
            log_level,
            f"Request completed: {method} {path} - {status_code} ({duration:.2f}s)",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "client_ip": client_ip,
                "user_id": user_id,
                "duration": duration,
            }
        )

        # Add custom headers for debugging (optional, only in development)
        # response.headers["X-Process-Time"] = str(duration)

        return response


def setup_logging(log_level: str = "INFO"):
    """
    Configure logging for the application

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/api_requests.log"),
            logging.StreamHandler(),
        ]
    )

    # Set log levels for specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # Reduce SQL query logs
    logging.getLogger("celery").setLevel(logging.INFO)
