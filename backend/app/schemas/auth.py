"""
Authentication schemas for API requests and responses
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import re

# API contract uses long language names; the DB enum stores short codes.
# Accept both on input, canonicalize to the short code, display long names.
LANGUAGE_INPUT_TO_CODE = {
    "en": "en", "english": "en",
    "pid": "pid", "pidgin": "pid",
    "ha": "ha", "hausa": "ha",
    "yo": "yo", "yoruba": "yo",
    "ig": "ig", "igbo": "ig",
}
LANGUAGE_CODE_TO_DISPLAY = {
    "en": "en",
    "pid": "pidgin",
    "ha": "hausa",
    "yo": "yoruba",
    "ig": "igbo",
}


class UserRegister(BaseModel):
    """Schema for user registration"""

    phone_number: str = Field(
        ...,
        description="Nigerian phone number (10-11 digits, starts with 0 or +234)"
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of the user"
    )
    language: str = Field(
        ...,
        description="Preferred language: en, pidgin, hausa, yoruba, igbo"
    )
    consent_given: bool = Field(
        ...,
        description="NDPA data consent (must be True)"
    )

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate Nigerian phone number"""
        # Remove spaces and dashes
        v = v.replace(" ", "").replace("-", "")

        # Pattern: +234XXXXXXXXXX or 0XXXXXXXXXX
        if not re.match(r"^(\+234|0)[7-9][0-1]\d{8}$", v):
            raise ValueError(
                "Invalid Nigerian phone number. Must be 11 digits starting with 070-091 or +234"
            )

        # Normalize to +234 format
        if v.startswith("0"):
            v = "+234" + v[1:]

        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language choice and canonicalize to the DB short code"""
        code = LANGUAGE_INPUT_TO_CODE.get(v.lower())
        if code is None:
            raise ValueError(
                "Language must be one of: en, pidgin, hausa, yoruba, igbo"
            )
        return code

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        """Ensure consent is given"""
        if not v:
            raise ValueError("Data consent is required to use MNAIR platform")
        return v


class UserLogin(BaseModel):
    """Schema for user login"""

    phone_number: str = Field(
        ...,
        description="Registered phone number"
    )
    password: Optional[str] = Field(
        None,
        description="Password (optional - MNAIR uses passwordless auth)"
    )


class Token(BaseModel):
    """Schema for JWT token response"""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class UserResponse(BaseModel):
    """Schema for user data in API responses"""

    id: int
    phone_number: str
    name: str
    language: str
    role: str
    current_day: int
    is_active: bool
    consent_given: bool
    created_at: datetime
    last_active_at: Optional[datetime] = None

    @field_validator("language", mode="before")
    @classmethod
    def language_display_name(cls, v):
        """Serialize the stored short code (or enum) as the API's long name"""
        value = getattr(v, "value", v)
        return LANGUAGE_CODE_TO_DISPLAY.get(value, value)

    class Config:
        from_attributes = True


class ProgressSummary(BaseModel):
    """Schema for user progress summary"""

    user_id: int
    current_day: int
    lessons_completed: int
    total_lessons: int
    completion_percentage: float
    average_quiz_score: Optional[float] = None
    days_active: int
    last_lesson_date: Optional[datetime] = None


class PasswordChange(BaseModel):
    """Schema for password change (admin users)"""

    old_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
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
