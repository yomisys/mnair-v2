"""
Certificate schemas for API requests and responses
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class CertificateResponse(BaseModel):
    """Schema for certificate data in API responses"""

    id: int
    certificate_id: str = Field(..., description="Unique certificate ID (MNAIR-YYYY-ID-RANDOM)")
    user_id: int
    learner_name: str
    learner_phone: str
    language: str
    total_lessons_completed: int
    average_quiz_score: float
    days_to_complete: int
    pdf_url: str = Field(..., description="MinIO object path")
    pdf_filename: str
    verification_hash: str = Field(..., description="SHA-256 hash for verification")
    verification_url: str = Field(..., description="Public verification URL")
    is_public: bool = Field(default=True, description="Allow public verification")
    issued_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class CertificateVerification(BaseModel):
    """
    Schema for certificate verification response (PUBLIC endpoint).

    Deliberately excludes phone number entirely, and never echoes the
    learner's stored name back — the caller must already supply the name
    they expect (see /verify/{certificate_id}?name=...), so this only ever
    confirms a match/no-match, it never discloses identity to a stranger
    who has nothing but a certificate code.
    """

    valid: bool = Field(..., description="Whether the certificate exists and the supplied name matches")
    certificate_id: str
    issued_date: datetime
    language: str
    average_score: float
    completion_grade: str = Field(..., description="Grade: Excellent, Very Good, Good, Pass")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "certificate_id": "MNAIR-2024-123-A3B9C",
                "issued_date": "2024-06-15T10:30:00",
                "language": "en",
                "average_score": 85.5,
                "completion_grade": "Very Good"
            }
        }


class CertificateGenerateRequest(BaseModel):
    """Schema for certificate generation request"""

    user_id: Optional[int] = Field(
        None,
        description="User ID (optional, defaults to current user)"
    )
    language: Optional[str] = Field(
        None,
        description="Certificate language (optional, defaults to user's language)"
    )


class CertificateDownloadResponse(BaseModel):
    """Schema for certificate download URL response"""

    certificate_id: str
    download_url: str = Field(..., description="Pre-signed URL for PDF download (expires in 7 days)")
    expires_in_seconds: int = Field(default=604800, description="URL expiration time")
    pdf_filename: str

    class Config:
        json_schema_extra = {
            "example": {
                "certificate_id": "MNAIR-2024-123-A3B9C",
                "download_url": "https://minio.example.com/mnair-certificates/certificates/MNAIR-2024-123-A3B9C.pdf?...",
                "expires_in_seconds": 604800,
                "pdf_filename": "MNAIR-2024-123-A3B9C.pdf"
            }
        }
