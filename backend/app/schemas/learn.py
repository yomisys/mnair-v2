"""
Schemas for the web learner app (/api/v1/learn).
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


PHONE_PATTERN = re.compile(r"^(\+234|234|0)[7-9][0-1]\d{8}$")


def normalize_phone(value: str) -> str:
    """Accept 080..., 234..., +234... and return +234XXXXXXXXXX."""
    v = value.replace(" ", "").replace("-", "").strip()
    if not PHONE_PATTERN.match(v):
        raise ValueError("Enter a valid Nigerian phone number, e.g. 08031234567")
    if v.startswith("0"):
        return "+234" + v[1:]
    if v.startswith("234"):
        return "+" + v
    return v


class PinMixin(BaseModel):
    pin: str = Field(..., description="Numeric PIN chosen by the learner")

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("PIN must contain digits only")
        if len(v) < 4 or len(v) > 8:
            raise ValueError("PIN must be 4 to 8 digits")
        return v


class EnrolRequest(PinMixin):
    phone_number: str
    consent_given: bool = Field(..., description="NDPA consent — must be true")
    name: Optional[str] = Field(None, max_length=255)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("consent_given")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must agree to the privacy notice to enrol")
        return v


class LoginRequest(PinMixin):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class MessageRequest(BaseModel):
    text: Optional[str] = Field(None, max_length=1000)
    interactive_id: Optional[str] = Field(None, max_length=64)

    @field_validator("interactive_id")
    @classmethod
    def _button_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("Invalid button id")
        return v


class PushSubscribeRequest(BaseModel):
    subscription: Dict[str, Any]
    user_agent: Optional[str] = Field(None, max_length=255)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., max_length=2048)


class LearnerSummary(BaseModel):
    id: int
    name: str
    name_confirmed: bool
    language: str
    current_day: int
    completed_days: int
    preferred_channel: Optional[str] = None


class ProgressOut(BaseModel):
    current_day: int
    lessons_completed: int
    total_lessons: int
    completion_percentage: float
    current_day_progress: int
    lessons_per_day: int = 5


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    learner: LearnerSummary
    messages: List[Dict[str, Any]] = []
    state: str


class TurnResponse(BaseModel):
    messages: List[Dict[str, Any]]
    state: str
    learner: LearnerSummary
    progress: Optional[ProgressOut] = None


class StateResponse(BaseModel):
    state: str
    learner: LearnerSummary
    history: List[Dict[str, Any]]
    progress: Optional[ProgressOut] = None
    push_subscribed: bool = False


class LearnConfig(BaseModel):
    telegram_link: Optional[str] = None
    vapid_public_key: Optional[str] = None
    pin_min_length: int = 4
    ussd_code: str
