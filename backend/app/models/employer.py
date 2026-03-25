from __future__ import annotations

"""
Employer model - Companies that verify learner certificates
Allows employers to search and verify MNAIR certificates
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Employer(Base):
    """
    Employer/Organization model
    Companies can register to verify learner certificates
    Used for recruitment and skills verification
    """
    __tablename__ = "employers"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Company Information
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Company/Organization name"
    )

    company_email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Company email for verification"
    )

    # Contact Person
    contact_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Primary contact person name"
    )

    contact_phone: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment="Contact phone number"
    )

    contact_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Contact person email"
    )

    # Company Details
    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Industry sector (e.g., Tech, Finance, Healthcare)"
    )

    company_size: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Company size: 1-10, 11-50, 51-200, 201-500, 500+"
    )

    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Company location in Nigeria (e.g., Lagos, Abuja)"
    )

    website: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Company website URL"
    )

    # Authentication
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hashed password for employer portal access"
    )

    # Account Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        comment="Account is active"
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        comment="Email verification completed"
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        comment="Admin approved (manual verification for MVP)"
    )

    # Usage Statistics
    certificates_verified_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of certificates verified"
    )

    last_verification_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Last certificate verification timestamp"
    )

    # API Access (optional for future)
    api_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        comment="API key for programmatic access"
    )

    api_requests_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of API requests made"
    )

    # NDPA Compliance
    terms_accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Accepted terms of service"
    )

    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="When terms were accepted"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        comment="Last successful login"
    )

    # Indexes
    __table_args__ = (
        Index("idx_employer_email", "company_email"),
        Index("idx_employer_active_approved", "is_active", "is_approved"),
        Index("idx_employer_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Employer {self.company_name}>"

    @property
    def is_ready_to_verify(self) -> bool:
        """Check if employer can verify certificates"""
        return self.is_active and self.is_verified and self.is_approved

    @property
    def needs_approval(self) -> bool:
        """Check if employer needs admin approval"""
        return self.is_verified and not self.is_approved

    def increment_verification_count(self) -> None:
        """Increment certificate verification counter"""
        self.certificates_verified_count += 1
        self.last_verification_at = datetime.utcnow()

    def increment_api_requests(self) -> None:
        """Increment API request counter"""
        self.api_requests_count += 1
