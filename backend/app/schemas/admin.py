"""Schemas for the admin back office (learners, certificates, payments)."""

from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.user import Language, UserRole
from app.schemas.learn import normalize_phone


class LearnerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    # A learner who changed SIM keeps their progress under the new number
    phone_number: Optional[str] = None
    email: Optional[str] = Field(None, max_length=255)
    language: Optional[Language] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None
    # Admin-panel password; required when promoting someone to admin
    password: Optional[str] = Field(None, min_length=10, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v is not None else v

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return " ".join(v.split()) if v is not None else v


class CertificateLinkRequest(BaseModel):
    days: int = Field(7, ge=1, le=30)
    allow_unpaid: bool = False


class VoidPaymentRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)
