"""
Pydantic schemas for API request/response validation
"""

from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    UserResponse,
)
from app.schemas.lesson import (
    LessonResponse,
    LessonProgressResponse,
    QuizSubmission,
    QuizResult,
)
from app.schemas.certificate import (
    CertificateResponse,
    CertificateVerification,
)

__all__ = [
    "UserRegister",
    "UserLogin",
    "Token",
    "UserResponse",
    "LessonResponse",
    "LessonProgressResponse",
    "QuizSubmission",
    "QuizResult",
    "CertificateResponse",
    "CertificateVerification",
]
