from __future__ import annotations

"""
Certificate model - Stores PDF certificate metadata
Links to MinIO for PDF storage, blockchain verification
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import hashlib
import secrets


class Certificate(Base):
    """
    Certificate model for program completion
    Issued after completing all 7 days
    Stored in MinIO, verified via blockchain hash
    """
    __tablename__ = "certificates"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Unique Certificate ID
    certificate_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique certificate identifier for verification"
    )

    # Foreign Key
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Learner Information (denormalized for certificate display)
    learner_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name as shown on certificate"
    )

    learner_phone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Phone number for verification. For a KingsChat learner, "
                "this is the 'kc:{conversation_id}' identity slot (see "
                "User.phone_number) -- widened from 15 to 64 chars 2026-07-17 "
                "for the same reason."
    )

    # Completion Details
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Language program completed in: en, pid, ha, yo, ig"
    )

    total_lessons_completed: Mapped[int] = mapped_column(
        default=35,
        comment="Total lessons completed (should be 35)"
    )

    average_quiz_score: Mapped[float] = mapped_column(
        nullable=False,
        comment="Average quiz score across all lessons (0.0 - 100.0)"
    )

    days_to_complete: Mapped[int] = mapped_column(
        nullable=False,
        comment="Number of days taken to complete program"
    )

    # File Storage (MinIO)
    pdf_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="MinIO URL to PDF certificate"
    )

    pdf_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PDF filename in MinIO bucket"
    )

    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        comment="PDF file size in bytes"
    )

    # Blockchain Verification
    verification_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="SHA-256 hash for blockchain verification"
    )

    blockchain_tx_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Blockchain transaction ID (optional for MVP)"
    )

    # Public Verification
    is_public: Mapped[bool] = mapped_column(
        default=True,
        comment="Allow public verification via certificate_id"
    )

    verification_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Public URL for certificate verification"
    )

    # Monetisation. access_type decides whether the certificate is a
    # verified credential (public /verify + PDF download) — see
    # CertificateAccess. Rows that pre-date this column are "free".
    access_type: Mapped[str] = mapped_column(
        String(20),
        default="free",
        server_default="free",
        nullable=False,
        comment="free | sponsored | paid | pending_payment"
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        comment="Sponsor that paid for this certificate"
    )
    sponsor_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Sponsor name as printed (snapshot — survives sponsor rename)"
    )

    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="certificates")

    # Indexes
    __table_args__ = (
        Index("idx_cert_issued_date", "issued_at"),
        Index("idx_cert_verification", "verification_hash"),
    )

    def __repr__(self) -> str:
        return f"<Certificate {self.certificate_id} for user={self.user_id}>"

    @staticmethod
    def generate_certificate_id(user_id: int, timestamp: Optional[datetime] = None) -> str:
        """
        Generate unique certificate ID
        Format: MNAIR-{YEAR}-{USER_ID}-{RANDOM}
        Example: MNAIR-2026-123-A7B9C2
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        year = timestamp.year
        random_suffix = secrets.token_hex(3).upper()

        return f"MNAIR-{year}-{user_id}-{random_suffix}"

    @staticmethod
    def generate_verification_hash(
        certificate_id: str,
        user_id: int,
        learner_name: str,
        issued_at: datetime
    ) -> str:
        """
        Generate SHA-256 verification hash for blockchain
        Hash components: certificate_id + user_id + name + timestamp
        """
        data = f"{certificate_id}{user_id}{learner_name}{issued_at.isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def generate_verification_url(self, base_url: str = "https://mnair.ng") -> str:
        """
        Generate public verification URL
        Example: https://mnair.ng/verify?code=MNAIR-2026-123-A7B9C2
        """
        return f"{base_url}/verify?code={self.certificate_id}"

    @property
    def is_valid(self) -> bool:
        """Check if certificate is valid (has all required fields)"""
        return bool(
            self.certificate_id
            and self.verification_hash
            and self.pdf_url
            and self.total_lessons_completed == 35
        )

    @property
    def is_verified(self) -> bool:
        """True when this is a verified credential (not awaiting payment)."""
        return (self.access_type or "free") != "pending_payment"

    @property
    def completion_grade(self) -> str:
        """Get completion grade based on average quiz score"""
        if self.average_quiz_score >= 90:
            return "Excellent"
        elif self.average_quiz_score >= 80:
            return "Very Good"
        elif self.average_quiz_score >= 70:
            return "Good"
        elif self.average_quiz_score >= 60:
            return "Pass"
        else:
            return "Below Pass"
