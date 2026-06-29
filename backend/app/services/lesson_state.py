"""
Lesson State Manager Service
Manages user progress through curriculum, quiz scoring, and day completion
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt


class QuizResult:
    """Result of a quiz attempt"""

    def __init__(
        self,
        score: float,
        correct_count: int,
        total_questions: int,
        passed: bool,
        attempt_number: int,
        can_retry: bool,
    ):
        self.score = score
        self.correct_count = correct_count
        self.total_questions = total_questions
        self.passed = passed
        self.attempt_number = attempt_number
        self.can_retry = can_retry

    def __repr__(self) -> str:
        return f"<QuizResult score={self.score}% passed={self.passed} attempt={self.attempt_number}>"


class ProgressSummary:
    """Summary of user's overall progress"""

    def __init__(
        self,
        user_id: int,
        current_day: int,
        lessons_completed: int,
        total_lessons: int,
        completion_percentage: float,
        current_day_progress: int,
        lessons_per_day: int = 5,
    ):
        self.user_id = user_id
        self.current_day = current_day
        self.lessons_completed = lessons_completed
        self.total_lessons = total_lessons
        self.completion_percentage = completion_percentage
        self.current_day_progress = current_day_progress
        self.lessons_per_day = lessons_per_day

    def __repr__(self) -> str:
        return f"<ProgressSummary user={self.user_id} day={self.current_day} progress={self.completion_percentage}%>"


class LessonStateManager:
    """
    Service to manage lesson progression and quiz attempts

    Core responsibilities:
    - Get next lesson for user
    - Record and score quiz attempts
    - Track lesson completion
    - Check day completion
    - Generate progress summaries
    """

    PASS_THRESHOLD = 60.0  # 60% to pass (3/5 questions)
    MAX_ATTEMPTS = 3  # Maximum quiz attempts per lesson
    QUESTIONS_PER_QUIZ = 5  # Expected questions per quiz
    LESSONS_PER_DAY = 5  # Topics per day

    TOPIC_ORDER = ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]

    def __init__(self, db: AsyncSession):
        """
        Initialize state manager with database session

        Args:
            db: Async database session
        """
        self.db = db

    async def get_next_lesson(
        self, user_id: int, language: str
    ) -> Optional[Lesson]:
        """
        Get the next incomplete lesson for user's current day

        Args:
            user_id: User ID
            language: User's preferred language

        Returns:
            Next lesson to complete, or None if day is complete
        """
        # Get user to find current day
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Find all lessons for current day and language
        lessons_query = select(Lesson).where(
            and_(
                Lesson.day == user.current_day,
                Lesson.language == language
            )
        )

        result = await self.db.execute(lessons_query)
        day_lessons = sorted(
            result.scalars().all(),
            key=lambda l: self.TOPIC_ORDER.index(l.topic) if l.topic in self.TOPIC_ORDER else 99
        )

        # Check which lessons are already completed
        for lesson in day_lessons:
            progress_query = select(LessonProgress).where(
                and_(
                    LessonProgress.user_id == user_id,
                    LessonProgress.lesson_id == lesson.id,
                    LessonProgress.is_completed == True
                )
            )
            result = await self.db.execute(progress_query)
            progress = result.scalar_one_or_none()

            if not progress:
                # This lesson is not completed yet
                return lesson

        # All lessons for this day are complete
        return None

    async def record_quiz_attempt(
        self,
        user_id: int,
        lesson_id: int,
        user_answers: List[int],
    ) -> QuizResult:
        """
        Record and score a quiz attempt

        Args:
            user_id: User ID
            lesson_id: Lesson ID
            user_answers: List of answer indices (0-3) selected by user

        Returns:
            QuizResult with score and pass/fail status
        """
        # Get lesson to extract correct answers
        result = await self.db.execute(
            select(Lesson).where(Lesson.id == lesson_id)
        )
        lesson = result.scalar_one_or_none()

        if not lesson:
            raise ValueError(f"Lesson {lesson_id} not found")

        # Validate quiz structure
        if not lesson.validate_quiz_structure():
            raise ValueError(f"Lesson {lesson_id} has invalid quiz structure")

        # Extract correct answers
        correct_answers = lesson.get_quiz_answers()

        # Validate user answers
        if len(user_answers) != len(correct_answers):
            raise ValueError(
                f"Expected {len(correct_answers)} answers, got {len(user_answers)}"
            )

        # Calculate score
        score, correct_count = QuizAttempt.calculate_score(
            user_answers, correct_answers
        )
        passed = QuizAttempt.is_passing_score(score)

        # Get or create lesson progress
        progress_query = select(LessonProgress).where(
            and_(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id == lesson_id
            )
        )
        result = await self.db.execute(progress_query)
        progress = result.scalar_one_or_none()

        if not progress:
            progress = LessonProgress(
                user_id=user_id,
                lesson_id=lesson_id,
                is_started=True,
            )
            self.db.add(progress)
            await self.db.flush()

        # Increment attempt count
        attempt_number = progress.quiz_attempts_count + 1
        progress.quiz_attempts_count = attempt_number

        # Check if can retry
        can_retry = attempt_number < self.MAX_ATTEMPTS

        # Create quiz attempt record
        quiz_attempt = QuizAttempt(
            user_id=user_id,
            lesson_id=lesson_id,
            attempt_number=attempt_number,
            user_answers=user_answers,
            correct_answers=correct_answers,
            score=score,
            questions_count=len(correct_answers),
            correct_count=correct_count,
            passed=passed,
        )
        self.db.add(quiz_attempt)

        # If passed, mark lesson as complete
        if passed:
            progress.mark_completed(score)

        await self.db.commit()

        return QuizResult(
            score=score,
            correct_count=correct_count,
            total_questions=len(correct_answers),
            passed=passed,
            attempt_number=attempt_number,
            can_retry=can_retry and not passed,
        )

    async def complete_lesson(self, user_id: int, lesson_id: int) -> bool:
        """
        Mark a lesson as viewed/started

        Args:
            user_id: User ID
            lesson_id: Lesson ID

        Returns:
            True if marked successfully
        """
        # Check if progress record exists
        progress_query = select(LessonProgress).where(
            and_(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id == lesson_id
            )
        )
        result = await self.db.execute(progress_query)
        progress = result.scalar_one_or_none()

        if not progress:
            # Create new progress record
            progress = LessonProgress(
                user_id=user_id,
                lesson_id=lesson_id,
                is_started=True,
            )
            self.db.add(progress)
            await self.db.commit()
            return True

        # Already exists
        return True

    async def is_day_complete(self, user_id: int, day: int) -> bool:
        """
        Check if user has completed all lessons for a given day

        Args:
            user_id: User ID
            day: Day number (1-7)

        Returns:
            True if all lessons for the day are completed
        """
        # Get user to find their language
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Count completed lessons for this day
        completed_query = select(func.count(LessonProgress.id)).select_from(
            LessonProgress
        ).join(
            Lesson, LessonProgress.lesson_id == Lesson.id
        ).where(
            and_(
                LessonProgress.user_id == user_id,
                LessonProgress.is_completed == True,
                Lesson.day == day,
                Lesson.language == user.language
            )
        )

        result = await self.db.execute(completed_query)
        completed_count = result.scalar()

        # Should have completed all 5 topics for the day
        return completed_count >= self.LESSONS_PER_DAY

    async def advance_to_next_day(self, user_id: int) -> bool:
        """
        Advance user to next day if current day is complete

        Args:
            user_id: User ID

        Returns:
            True if advanced, False if current day not complete or already on day 7
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Check if current day is complete
        if not await self.is_day_complete(user_id, user.current_day):
            return False

        # Check if already on final day
        if user.current_day >= 7:
            return False

        # Advance to next day
        user.current_day += 1
        user.completed_days += 1
        await self.db.commit()

        return True

    async def get_user_progress(self, user_id: int) -> Optional[ProgressSummary]:
        """
        Get comprehensive progress summary for user

        Args:
            user_id: User ID

        Returns:
            ProgressSummary or None if user not found
        """
        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Count total completed lessons
        completed_query = select(func.count(LessonProgress.id)).where(
            and_(
                LessonProgress.user_id == user_id,
                LessonProgress.is_completed == True
            )
        )
        result = await self.db.execute(completed_query)
        lessons_completed = result.scalar() or 0

        # Total lessons for user's language (35 lessons)
        total_lessons = 35

        # Calculate overall completion percentage
        completion_percentage = (lessons_completed / total_lessons) * 100.0

        # Count completed lessons for current day
        current_day_query = select(func.count(LessonProgress.id)).select_from(
            LessonProgress
        ).join(
            Lesson, LessonProgress.lesson_id == Lesson.id
        ).where(
            and_(
                LessonProgress.user_id == user_id,
                LessonProgress.is_completed == True,
                Lesson.day == user.current_day,
                Lesson.language == user.language
            )
        )
        result = await self.db.execute(current_day_query)
        current_day_progress = result.scalar() or 0

        return ProgressSummary(
            user_id=user_id,
            current_day=user.current_day,
            lessons_completed=lessons_completed,
            total_lessons=total_lessons,
            completion_percentage=completion_percentage,
            current_day_progress=current_day_progress,
            lessons_per_day=self.LESSONS_PER_DAY,
        )

    async def get_quiz_attempts(
        self, user_id: int, lesson_id: int
    ) -> List[QuizAttempt]:
        """
        Get all quiz attempts for a lesson

        Args:
            user_id: User ID
            lesson_id: Lesson ID

        Returns:
            List of quiz attempts, ordered by attempt number
        """
        query = select(QuizAttempt).where(
            and_(
                QuizAttempt.user_id == user_id,
                QuizAttempt.lesson_id == lesson_id
            )
        ).order_by(QuizAttempt.attempt_number)

        result = await self.db.execute(query)
        return list(result.scalars().all())
