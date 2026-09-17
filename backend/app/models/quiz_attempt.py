from __future__ import annotations

"""
QuizAttempt model - Records individual quiz attempts
Stores user answers, scores, and attempt metadata
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Float, Boolean, DateTime, JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class QuizAttempt(Base):
    """
    Records individual quiz attempts
    Allows max 3 attempts per lesson
    Pass threshold: 60% (3/5 questions correct)
    """
    __tablename__ = "quiz_attempts"

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

    # Attempt Metadata
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Attempt number (1, 2, or 3)"
    )

    # Quiz Answers
    user_answers: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="Array of user's answer indices: [0, 2, 1, 3, 0]"
    )

    correct_answers: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="Array of correct answer indices: [0, 1, 2, 3, 0]"
    )

    # Scoring
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Score as percentage (0.0 - 100.0)"
    )

    questions_count: Mapped[int] = mapped_column(
        Integer,
        default=5,
        comment="Total number of questions"
    )

    correct_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of correct answers"
    )

    passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        index=True,
        comment="Passed threshold (>= 60%)"
    )

    # Channel Information
    channel_used: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="Channel used: telegram, web, ussd, sms, or kingschat"
    )

    # Timing
    time_taken_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Time taken to complete quiz (seconds)"
    )

    # Timestamps
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="quiz_attempts")
    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="quiz_attempts")

    # Indexes
    __table_args__ = (
        Index("idx_attempt_user_lesson", "user_id", "lesson_id"),
        Index("idx_attempt_passed", "passed"),
        Index("idx_attempt_score", "score"),
    )

    def __repr__(self) -> str:
        return f"<QuizAttempt user={self.user_id} lesson={self.lesson_id} attempt={self.attempt_number} score={self.score}%>"

    @property
    def is_passing(self) -> bool:
        """Check if attempt passed (>= 60%)"""
        return self.passed

    @property
    def incorrect_count(self) -> int:
        """Get number of incorrect answers"""
        return self.questions_count - self.correct_count

    @property
    def accuracy_percentage(self) -> float:
        """Get accuracy as percentage"""
        return self.score

    def get_detailed_results(self) -> list[dict]:
        """
        Get detailed results for each question
        Returns list of dicts with question_index, user_answer, correct_answer, is_correct
        """
        if not isinstance(self.user_answers, list) or not isinstance(self.correct_answers, list):
            return []

        results = []
        for i, (user_ans, correct_ans) in enumerate(zip(self.user_answers, self.correct_answers)):
            results.append({
                "question_index": i,
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": user_ans == correct_ans
            })

        return results

    @staticmethod
    def calculate_score(user_answers: list[int], correct_answers: list[int]) -> tuple[float, int]:
        """
        Calculate quiz score
        Returns (score_percentage, correct_count)
        """
        if not user_answers or not correct_answers:
            return 0.0, 0

        total = len(correct_answers)
        correct = sum(1 for ua, ca in zip(user_answers, correct_answers) if ua == ca)
        score = (correct / total) * 100.0

        return score, correct

    @staticmethod
    def is_passing_score(score: float) -> bool:
        """Check if score meets passing threshold (60%)"""
        return score >= 60.0
