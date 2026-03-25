"""
API routers for MNAIR platform
"""

from app.routers.auth import router as auth_router
from app.routers.lessons import router as lessons_router
from app.routers.certificates import router as certificates_router

__all__ = [
    "auth_router",
    "lessons_router",
    "certificates_router",
]
