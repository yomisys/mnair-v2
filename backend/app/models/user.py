from __future__ import annotations

"""
User model - Learners, Admins, and Employers
Nigerian-specific: phone number validation, language preferences
NDPA compliant: consent tracking, data retention
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import List,Optional
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.config import settings


class UserRole(str, Enum):
    """User role types"""
    LEARNER = "learner"
    ADMIN = "admin"
    EMPLOYER = "employer"


class Language(str, Enum):
    """Supported languages for Nigerian context"""
    ENGLISH = "en"
    PIDGIN = "pid"
    HAUSA = "ha"
    YORUBA = "yo"
    IGBO = "ig"


class User(Base):
    """
    User model for all platform users
    Supports learners (via WhatsApp/USSD), admins, and employers
    """
    __tablename__ = "users"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Identity
    phone_number: Mapped[str] = mapped_column(
        String(15),
        unique=True,
        index=True,
        comment="Nigerian phone: 080XXXXXXXX or 234XXXXXXXXXX"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)

    # Authentication (for admin/employer only)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))

    # Role & Permissions
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.LEARNER,
        nullable=False,
        index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Learner-specific
    language: Mapped[Language] = mapped_column(
        SQLEnum(Language),
        default=Language.ENGLISH,
        nullable=False,
        index=True,
        comment="Preferred language for lessons"
    )
    current_day: Mapped[int] = mapped_column(
        default=1,
        comment="Current day in 7-day curriculum"
    )
    completed_days: Mapped[int] = mapped_column(
        default=0,
        comment="Number of days completed (0-7)"
    )

    # Preferred communication channel
    preferred_channel: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="whatsapp, ussd, or sms"
    )

    # NDPA Compliance Fields (Nigeria Data Protection Act 2023)
    consent_given: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="User explicitly consented to data processing"
    )
    consent_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    data_retention_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow() + timedelta(days=settings.DATA_RETENTION_DAYS),
        comment="Auto-delete user data after this date (NDPA compliance)"
    )

    # Telco Information (for Nigerian network optimization)
    network_operator: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="MTN, Glo, Airtel, 9mobile - detected from phone prefix"
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
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Last interaction via any channel"
    )

    # Relationships
    lesson_progress: Mapped[List["LessonProgress"]] = relationship(
        "LessonProgress",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    quiz_attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    certificates: Mapped[List["Certificate"]] = relationship(
        "Certificate",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_user_phone_role", "phone_number", "role"),
        Index("idx_user_language_active", "language", "is_active"),
        Index("idx_user_current_day", "current_day"),
        Index("idx_user_retention_date", "data_retention_date"),
    )

    def __repr__(self) -> str:
        return f"<User {self.phone_number} ({self.role.value})>"

    @property
    def is_learner(self) -> bool:
        """Check if user is a learner"""
        return self.role == UserRole.LEARNER

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        return self.role == UserRole.ADMIN

    @property
    def is_employer(self) -> bool:
        """Check if user is an employer"""
        return self.role == UserRole.EMPLOYER

    @property
    def has_completed_program(self) -> bool:
        """Check if learner completed all 7 days"""
        return self.completed_days >= 7

    def detect_network_operator(self) -> Optional[str]:
        """
        Detect Nigerian network operator from phone number prefix
        MTN: 0803, 0806, 0810, 0813, 0814, 0816, 0903, 0906, 0913, 0916
        Glo: 0805, 0807, 0811, 0815, 0905, 0915
        Airtel: 0802, 0808, 0812, 0901, 0902, 0904, 0907, 0912
        9mobile: 0809, 0817, 0818, 0909, 0908
        """
        phone = self.phone_number.replace("+234", "0")

        if not phone.startswith("0"):
            return None

        prefix = phone[:4]

        mtn_prefixes = ["0803", "0806", "0810", "0813", "0814", "0816", "0903", "0906", "0913", "0916"]
        glo_prefixes = ["0805", "0807", "0811", "0815", "0905", "0915"]
        airtel_prefixes = ["0802", "0808", "0812", "0901", "0902", "0904", "0907", "0912"]
        ninemobile_prefixes = ["0809", "0817", "0818", "0909", "0908"]

        if prefix in mtn_prefixes:
            return "MTN"
        elif prefix in glo_prefixes:
            return "Glo"
        elif prefix in airtel_prefixes:
            return "Airtel"
        elif prefix in ninemobile_prefixes:
            return "9mobile"

        return None
