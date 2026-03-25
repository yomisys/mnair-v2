"""
Employer schemas for API requests and responses
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, field_validator
from datetime import datetime
import re


class EmployerRegister(BaseModel):
    """Schema for employer registration"""

    company_name: str = Field(..., min_length=2, max_length=255)
    company_email: EmailStr = Field(..., description="Company email address")
    contact_name: str = Field(..., min_length=2, max_length=255)
    contact_phone: str = Field(..., description="Contact phone number")
    contact_email: EmailStr = Field(..., description="Contact person email")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    industry: Optional[str] = Field(None, max_length=100)
    company_size: Optional[str] = Field(None, description="1-10, 11-50, 51-200, 201-500, 500+")
    location: Optional[str] = Field(None, description="Location in Nigeria")
    website: Optional[str] = Field(None, max_length=255)
    terms_accepted: bool = Field(..., description="Must accept terms of service")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("terms_accepted")
    @classmethod
    def validate_terms(cls, v: bool) -> bool:
        """Ensure terms are accepted"""
        if not v:
            raise ValueError("Must accept terms of service")
        return v


class EmployerLogin(BaseModel):
    """Schema for employer login"""

    company_email: EmailStr = Field(..., description="Company email address")
    password: str = Field(..., description="Password")


class EmployerResponse(BaseModel):
    """Schema for employer data in API responses"""

    id: int
    company_name: str
    company_email: str
    contact_name: str
    contact_phone: str
    contact_email: str
    industry: Optional[str] = None
    company_size: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_approved: bool
    certificates_verified_count: int
    last_verification_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CertificateSearchRequest(BaseModel):
    """Schema for certificate search by employer"""

    phone_number: Optional[str] = Field(None, description="Search by phone number")
    name: Optional[str] = Field(None, description="Search by learner name")
    certificate_id: Optional[str] = Field(None, description="Search by certificate ID")


class CertificateSearchResult(BaseModel):
    """Schema for certificate search results"""

    certificate_id: str
    learner_name: str
    learner_phone: str
    issued_date: datetime
    language: str
    average_quiz_score: float
    days_to_complete: int
    completion_grade: str
    verification_hash: str
    verification_url: str

    class Config:
        from_attributes = True
