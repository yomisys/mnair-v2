from __future__ import annotations

"""
Sponsorship + payments.

A sponsor (church, company, state, NGO) funds certificates for its people.
Learners join under a SponsorCode; when one of them is certified a
SponsorCharge is written at the sponsor's per-certificate price. Payments
(deposit, monthly balance, or a learner buying their own verified
certificate) are Payment rows confirmed by Paystack.

Billing is computed, never stored as a running total:
    amount due = sum(charges) - sum(successful sponsor payments)
so the deposit is simply the first payment and is used up by the first
certificates — there is no separate "credit" ledger to drift out of sync.

SponsorCharge deliberately keeps no learner PII and survives learner
erasure (user_id SET NULL): a learner deleting their account under the NDPA
must not silently rewrite a sponsor's invoice.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SponsorPackage(str, Enum):
    COMMUNITY = "community"
    ORGANISATION = "organisation"
    ENTERPRISE = "enterprise"
    NATIONAL = "national"


# Published price list (see the sponsor pricing sheet). Kobo.
PACKAGE_DEFAULTS = {
    SponsorPackage.COMMUNITY: {"price_per_certificate_kobo": 250_000, "deposit_kobo": 12_500_000},
    SponsorPackage.ORGANISATION: {"price_per_certificate_kobo": 200_000, "deposit_kobo": 100_000_000},
    SponsorPackage.ENTERPRISE: {"price_per_certificate_kobo": 150_000, "deposit_kobo": 750_000_000},
    # Negotiated per contract — admin must set both explicitly.
    SponsorPackage.NATIONAL: {"price_per_certificate_kobo": None, "deposit_kobo": None},
}


class PaymentPurpose(str, Enum):
    CERTIFICATE = "certificate"          # learner buys own verified certificate
    SPONSOR_DEPOSIT = "sponsor_deposit"  # upfront, credited against first certificates
    SPONSOR_BALANCE = "sponsor_balance"  # monthly statement settlement
    SPONSOR_MANUAL = "sponsor_manual"    # bank transfer recorded by an admin


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ABANDONED = "abandoned"
    VOIDED = "voided"                    # admin reversed a mis-recorded bank transfer


class CertificateAccess(str, Enum):
    FREE = "free"                        # issued before/without the paywall
    SPONSORED = "sponsored"              # paid for by a sponsor
    PAID = "paid"                        # learner paid
    PENDING_PAYMENT = "pending_payment"  # earned, verified copy not yet unlocked

    @classmethod
    def verified_values(cls) -> set:
        return {cls.FREE.value, cls.SPONSORED.value, cls.PAID.value}


class Organization(Base):
    """A sponsor. Also the sponsor-portal login (token sub 'sponsor:{id}')."""
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    package: Mapped[str] = mapped_column(String(20), nullable=False, default=SponsorPackage.COMMUNITY.value)

    price_per_certificate_kobo: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_kobo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    learner_cap: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Max learners across all this sponsor's codes; NULL = no cap"
    )

    contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(32))

    # Sponsor portal sign-in
    portal_email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))

    # Logo printed on certificates — object name in the MinIO bucket
    logo_object: Mapped[Optional[str]] = mapped_column(String(255))

    # White-label landing page (/s/<code>), edited by the sponsor in its portal
    brand_color: Mapped[Optional[str]] = mapped_column(String(7), comment="#RRGGBB")
    tagline: Mapped[Optional[str]] = mapped_column(String(160))
    welcome_message: Mapped[Optional[str]] = mapped_column(Text)
    website_url: Mapped[Optional[str]] = mapped_column(String(500))

    # The sponsor's advert to its own learners (landing page + /learn).
    # ad_suspended is the admin's override; the sponsor cannot clear it.
    ad_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ad_headline: Mapped[Optional[str]] = mapped_column(String(120))
    ad_body: Mapped[Optional[str]] = mapped_column(Text)
    ad_cta_label: Mapped[Optional[str]] = mapped_column(String(40))
    ad_cta_url: Mapped[Optional[str]] = mapped_column(String(500))
    ad_image_object: Mapped[Optional[str]] = mapped_column(String(255))
    ad_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    codes: Mapped[List["SponsorCode"]] = relationship(
        "SponsorCode", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.id} {self.name!r}>"


class SponsorCode(Base):
    """A code learners enter (or a t.me/<bot>?start=<CODE> deep link)."""
    __tablename__ = "sponsor_codes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), comment="e.g. 'Youth church, Ikeja'")
    max_enrolments: Mapped[Optional[int]] = mapped_column(Integer)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="codes")

    def __repr__(self) -> str:
        return f"<SponsorCode {self.code}>"


class SponsorCharge(Base):
    """One billable certificate. Written once, at issue time, at the price
    then in force — a later price change never re-prices past certificates."""
    __tablename__ = "sponsor_charges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sponsor_code_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sponsor_codes.id", ondelete="SET NULL"))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    certificate_code: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("certificate_code", name="uq_sponsor_charge_certificate"),
        Index("idx_sponsor_charge_org_date", "organization_id", "created_at"),
    )


class Payment(Base):
    """A Paystack transaction (or an admin-recorded bank transfer)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentStatus.PENDING.value, index=True)
    amount_kobo: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    authorization_url: Mapped[Optional[str]] = mapped_column(String(500))
    access_code: Mapped[Optional[str]] = mapped_column(String(100))
    channel: Mapped[Optional[str]] = mapped_column(String(30), comment="card, bank_transfer, ussd, ...")
    gateway_response: Mapped[Optional[str]] = mapped_column(String(255))
    note: Mapped[Optional[str]] = mapped_column(String(255))

    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_payment_org_status", "organization_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.reference} {self.purpose} {self.status}>"
