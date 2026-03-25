from __future__ import annotations

"""
Lesson model - Stores curriculum content
35 topics × 5 languages = 175 lessons
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Text, JSON, Index, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Lesson(Base):
    """
    Lesson content model
    Each lesson has: title, content, quiz questions
    Supports 5 Nigerian languages
    """
    __tablename__ = "lessons"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Unique lesson identifier (e.g., "day1_what_is_ai_en")
    lesson_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique identifier: day{N}_{topic}_{language}"
    )

    # Curriculum Structure
    day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="Day number (1-7)"
    )

    topic: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Topic: what_is_ai, how_ai_works, ai_in_nigeria, ai_tools, ai_ethics"
    )

    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
        comment="Language code: en, pid, ha, yo, ig"
    )

    # Content
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Lesson title"
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Main lesson text (250-300 words)"
    )

    # Quiz Questions (stored as JSON array)
    quiz: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="""
        Quiz questions as JSON array:
        [
            {
                "question": "What is AI?",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct": 0
            },
            ...
        ]
        """
    )

    # Metadata
    estimated_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        comment="Estimated time to complete (minutes)"
    )

    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Content word count"
    )

    # Media (optional - images/audio for low bandwidth)
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Optional image URL (<50KB for Nigerian bandwidth)"
    )

    audio_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Optional audio narration URL"
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

    # Relationships
    progress_records: Mapped[List["LessonProgress"]] = relationship(
        "LessonProgress",
        back_populates="lesson",
        cascade="all, delete-orphan"
    )

    quiz_attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt",
        back_populates="lesson",
        cascade="all, delete-orphan"
    )

    # Indexes and Constraints
    __table_args__ = (
        Index("idx_lesson_day_language", "day", "language"),
        Index("idx_lesson_topic_language", "topic", "language"),
        UniqueConstraint("day", "topic", "language", name="uq_lesson_day_topic_lang"),
    )

    def __repr__(self) -> str:
        return f"<Lesson {self.lesson_id}>"

    @property
    def quiz_question_count(self) -> int:
        """Get number of quiz questions"""
        return len(self.quiz) if isinstance(self.quiz, list) else 0

    @property
    def is_english(self) -> bool:
        """Check if lesson is in English"""
        return self.language == "en"

    @property
    def is_pidgin(self) -> bool:
        """Check if lesson is in Pidgin"""
        return self.language == "pid"

    def get_quiz_answers(self) -> list[int]:
        """Extract correct answer indices from quiz"""
        if not isinstance(self.quiz, list):
            return []
        return [q.get("correct", -1) for q in self.quiz]

    def validate_quiz_structure(self) -> bool:
        """Validate quiz JSON structure"""
        if not isinstance(self.quiz, list):
            return False

        required_keys = {"question", "options", "correct"}

        for q in self.quiz:
            if not isinstance(q, dict):
                return False
            if not required_keys.issubset(q.keys()):
                return False
            if not isinstance(q["options"], list) or len(q["options"]) != 4:
                return False
            if not isinstance(q["correct"], int) or q["correct"] not in [0, 1, 2, 3]:
                return False

        return True
