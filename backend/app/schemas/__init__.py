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
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    DashboardOverview,
)
from app.schemas.employer import (
    EmployerRegister,
    EmployerLogin,
    EmployerResponse,
    CertificateSearchRequest,
    CertificateSearchResult,
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
    "AnalyticsResponse",
    "AnalyticsSummary",
    "DashboardOverview",
    "EmployerRegister",
    "EmployerLogin",
    "EmployerResponse",
    "CertificateSearchRequest",
    "CertificateSearchResult",
]
