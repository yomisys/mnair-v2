from __future__ import annotations

"""
LessonProgress model - Tracks user progress through curriculum
Records completion status, scores, and timestamps
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Boolean, Float, DateTime, ForeignKey, Index, UniqueConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class LessonProgress(Base):
    """
    Tracks individual user progress on each lesson
    One record per user per lesson
    """
    __tablename__ = "lesson_progress"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Progress Status
    is_started: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="User has viewed the lesson content"
    )

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        comment="User has successfully completed quiz (>= 60% score)"
    )

    # Quiz Performance
    quiz_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Final quiz score (0.0 - 100.0)"
    )

    quiz_attempts_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of quiz attempts (max 3)"
    )

    passed_quiz: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Achieved >= 60% on quiz"
    )

    # Engagement Metrics
    time_spent_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Total time spent on lesson (seconds)"
    )

    # Channel Information
    channel_used: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="Channel used: whatsapp, ussd, or sms"
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        comment="When user first opened the lesson"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        comment="When user completed the lesson (passed quiz)"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="lesson_progress")
    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="progress_records")

    # Indexes and Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson_progress"),
        Index("idx_progress_user_completed", "user_id", "is_completed"),
        Index("idx_progress_completion_date", "completed_at"),
    )

    def __repr__(self) -> str:
        status = "completed" if self.is_completed else "in_progress"
        return f"<LessonProgress user={self.user_id} lesson={self.lesson_id} status={status}>"

    @property
    def is_in_progress(self) -> bool:
        """Check if lesson is in progress (started but not completed)"""
        return self.is_started and not self.is_completed

    @property
    def can_retry_quiz(self) -> bool:
        """Check if user can retry quiz (max 3 attempts)"""
        return self.quiz_attempts_count < 3

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage (0.0 - 100.0)"""
        if self.is_completed:
            return 100.0
        elif self.is_started:
            return 50.0
        return 0.0

    def calculate_time_spent(self) -> Optional[int]:
        """Calculate time spent on lesson (seconds)"""
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.utcnow()
        delta = end_time - self.started_at
        return int(delta.total_seconds())

    def mark_completed(self, score: float) -> None:
        """Mark lesson as completed with final score"""
        self.is_completed = True
        self.quiz_score = score
        self.passed_quiz = score >= 60.0
        self.completed_at = datetime.utcnow()
        self.time_spent_seconds = self.calculate_time_spent()
