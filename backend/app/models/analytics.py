from __future__ import annotations

"""
Analytics model - Aggregated KPI metrics
Daily snapshots of platform performance
Optimized for dashboard queries
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Analytics(Base):
    """
    Daily analytics snapshots
    Aggregated metrics for dashboard performance
    Pre-calculated to avoid expensive real-time queries
    """
    __tablename__ = "analytics"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Date (one record per day)
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        unique=True,
        index=True,
        comment="Analytics date (YYYY-MM-DD)"
    )

    # User Metrics
    total_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total registered users (cumulative)"
    )

    new_users_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="New user registrations today"
    )

    active_users_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Users who interacted today"
    )

    active_users_7d: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Active users in last 7 days"
    )

    active_users_30d: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Active users in last 30 days"
    )

    # Completion Metrics
    users_in_progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Users currently taking lessons (days 1-6)"
    )

    users_completed_program: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Users who completed all 7 days (cumulative)"
    )

    completions_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Program completions today"
    )

    completion_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="Overall completion rate (0.0 - 100.0)"
    )

    # Lesson Metrics
    total_lessons_completed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total lesson completions (cumulative)"
    )

    lessons_completed_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Lessons completed today"
    )

    average_lessons_per_user: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="Average lessons completed per user"
    )

    # Quiz Performance
    total_quiz_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total quiz attempts (cumulative)"
    )

    quiz_attempts_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Quiz attempts today"
    )

    average_quiz_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="Average quiz score across all attempts (0.0 - 100.0)"
    )

    quiz_pass_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="Percentage of quiz attempts that passed (>= 60%)"
    )

    # Channel Distribution
    channel_distribution: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="""
        Active users by channel:
        {
            "whatsapp": 12500,
            "ussd": 8200,
            "sms": 1300
        }
        """
    )

    # Language Distribution
    language_distribution: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="""
        Users by language:
        {
            "en": 10000,
            "pid": 5000,
            "ha": 3000,
            "yo": 2500,
            "ig": 1500
        }
        """
    )

    # Day Distribution (users by current day)
    day_distribution: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="""
        Users by current day:
        {
            "1": 3000,
            "2": 2500,
            "3": 2000,
            ...
        }
        """
    )

    # Certificate Metrics
    certificates_issued: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total certificates issued (cumulative)"
    )

    certificates_issued_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Certificates issued today"
    )

    certificates_verified_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Certificate verifications by employers today"
    )

    # Engagement Metrics
    average_session_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Average session duration (seconds)"
    )

    messages_sent_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total messages sent to users today (all channels)"
    )

    # Network Operator Distribution (Nigerian telcos)
    network_distribution: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="""
        Users by telco:
        {
            "MTN": 8000,
            "Glo": 4500,
            "Airtel": 5500,
            "9mobile": 2000
        }
        """
    )

    # Top Performing Lessons (most completed)
    top_lessons: Mapped[list] = mapped_column(
        JSON,
        default=list,
        comment="""
        Top 10 most completed lessons:
        [
            {"lesson_id": "day1_what_is_ai_en", "completions": 9500},
            ...
        ]
        """
    )

    # Employer Metrics
    total_employers: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total registered employers (cumulative)"
    )

    new_employers_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="New employer registrations today"
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

    # Indexes
    __table_args__ = (
        Index("idx_analytics_date", "date"),
        Index("idx_analytics_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Analytics {self.date} users={self.total_users}>"

    @property
    def user_retention_rate(self) -> float:
        """Calculate 7-day retention rate"""
        if self.total_users == 0:
            return 0.0
        return (self.active_users_7d / self.total_users) * 100.0

    @property
    def daily_active_rate(self) -> float:
        """Calculate daily active rate (DAU/MAU)"""
        if self.active_users_30d == 0:
            return 0.0
        return (self.active_users_today / self.active_users_30d) * 100.0

    def get_channel_percentage(self, channel: str) -> float:
        """Get percentage of users using specific channel"""
        if not isinstance(self.channel_distribution, dict):
            return 0.0

        total = sum(self.channel_distribution.values())
        if total == 0:
            return 0.0

        return (self.channel_distribution.get(channel, 0) / total) * 100.0

    def get_language_percentage(self, language: str) -> float:
        """Get percentage of users using specific language"""
        if not isinstance(self.language_distribution, dict):
            return 0.0

        total = sum(self.language_distribution.values())
        if total == 0:
            return 0.0

        return (self.language_distribution.get(language, 0) / total) * 100.0
