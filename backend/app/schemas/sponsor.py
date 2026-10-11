"""
Schemas for sponsors (admin + sponsor portal) and payments.
All money is kobo (int).
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.sponsor import PACKAGE_DEFAULTS, SponsorPackage
from app.services.sponsorship import CODE_PATTERN, normalize_code


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    package: SponsorPackage = SponsorPackage.COMMUNITY
    contact_email: EmailStr
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=32)
    # Override the package price list (required for 'national')
    price_per_certificate_kobo: Optional[int] = Field(None, gt=0)
    deposit_kobo: Optional[int] = Field(None, ge=0)
    learner_cap: Optional[int] = Field(None, gt=0)
    # Sponsor portal login (optional at creation; can be set later)
    portal_email: Optional[EmailStr] = None
    portal_password: Optional[str] = Field(None, min_length=10, max_length=128)
    # First code; generated from the name when omitted
    first_code: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _prices(self) -> "OrganizationCreate":
        defaults = PACKAGE_DEFAULTS[self.package]
        if self.price_per_certificate_kobo is None:
            self.price_per_certificate_kobo = defaults["price_per_certificate_kobo"]
        if self.deposit_kobo is None:
            self.deposit_kobo = defaults["deposit_kobo"]
        if self.price_per_certificate_kobo is None or self.deposit_kobo is None:
            raise ValueError("National package: set price_per_certificate_kobo and deposit_kobo explicitly")
        if bool(self.portal_email) != bool(self.portal_password):
            raise ValueError("Set portal_email and portal_password together")
        return self

    @field_validator("first_code")
    @classmethod
    def _code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = normalize_code(v)
        if not CODE_PATTERN.match(v):
            raise ValueError("Codes are 3-40 letters, digits or dashes")
        return v


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    package: Optional[SponsorPackage] = None
    contact_email: Optional[EmailStr] = None
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=32)
    price_per_certificate_kobo: Optional[int] = Field(None, gt=0)
    deposit_kobo: Optional[int] = Field(None, ge=0)
    learner_cap: Optional[int] = Field(None, gt=0)
    clear_learner_cap: bool = False
    is_active: Optional[bool] = None
    portal_email: Optional[EmailStr] = None
    portal_password: Optional[str] = Field(None, min_length=10, max_length=128)
    notes: Optional[str] = Field(None, max_length=2000)


class CodeCreate(BaseModel):
    code: Optional[str] = None
    label: Optional[str] = Field(None, max_length=255)
    max_enrolments: Optional[int] = Field(None, gt=0)
    expires_at: Optional[datetime] = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = normalize_code(v)
        if not CODE_PATTERN.match(v):
            raise ValueError("Codes are 3-40 letters, digits or dashes")
        return v


class CodeUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=255)
    max_enrolments: Optional[int] = Field(None, gt=0)
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class CodeOut(BaseModel):
    id: int
    code: str
    label: Optional[str]
    max_enrolments: Optional[int]
    expires_at: Optional[datetime]
    is_active: bool
    join_url: str
    telegram_url: Optional[str]


class SponsorLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class SponsorPayRequest(BaseModel):
    purpose: Literal["deposit", "balance"]


class AdminPaymentLinkRequest(BaseModel):
    purpose: Literal["deposit", "balance"]
    # Optional explicit amount; default = outstanding deposit / amount due
    amount_kobo: Optional[int] = Field(None, ge=10_000)


class ManualPaymentRequest(BaseModel):
    amount_kobo: int = Field(..., gt=0)
    note: str = Field(..., min_length=3, max_length=255, description="e.g. bank transfer ref, payer, date")
    paid_at: Optional[datetime] = None


class CheckoutOut(BaseModel):
    reference: str
    authorization_url: str
    amount_kobo: int
    purpose: str


class PaymentStatusOut(BaseModel):
    reference: str
    status: str
    purpose: str
    amount_kobo: int
