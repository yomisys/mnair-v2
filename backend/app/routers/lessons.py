"""
Lesson and Quiz API endpoints
Handles lesson retrieval, progress tracking, and quiz submissions
"""

from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt
from app.schemas.lesson import (
    LessonResponse,
    LessonProgressResponse,
    QuizSubmission,
    QuizResult,
    NextLessonResponse,
    DayProgressResponse,
)
from app.utils.auth import get_current_user
from app.services.lesson_state import LessonStateManager

router = APIRouter(prefix="/api/v1/lessons", tags=["Lessons"])


@router.get("/next", response_model=NextLessonResponse)
async def get_next_lesson(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the next lesson for the current user

    Returns:
    - Next incomplete lesson for user's current day
    - Status message if day/course is complete
    """
    manager = LessonStateManager(db)

    # Get next lesson
    next_lesson = await manager.get_next_lesson(
        user_id=current_user.id,
        language=current_user.language
    )

    # Check if day is complete
    day_complete = await manager.is_day_complete(
        user_id=current_user.id,
        day=current_user.current_day
    )

    # Check if course is complete (day 7 done)
    course_complete = current_user.current_day >= 7 and day_complete

    if course_complete:
        message = "Congratulations! You've completed the entire 7-day AI course. Download your certificate!"
    elif day_complete:
        message = f"Day {current_user.current_day} complete! Ready to start Day {current_user.current_day + 1}?"
    elif next_lesson:
        message = f"Continue learning with your next lesson: {next_lesson.title}"
    else:
        message = "No lessons available"

    return NextLessonResponse(
        lesson=next_lesson,
        day_complete=day_complete,
        course_complete=course_complete,
        message=message
    )


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson_by_id(
    lesson_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific lesson by ID

    Returns lesson content and quiz questions (without correct answers)
    """
    result = await db.execute(
        select(Lesson).where(
            Lesson.id == lesson_id,
            Lesson.language == current_user.language
        )
    )
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found for language {current_user.language}"
        )

    # Check if user has access to this day
    if lesson.day > current_user.current_day:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Complete Day {current_user.current_day} before accessing Day {lesson.day}"
        )

    return lesson


@router.get("/day/{day}", response_model=List[LessonResponse])
async def get_lessons_by_day(
    day: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all lessons for a specific day

    Returns 5 lessons (one for each topic: what_is_ai, how_ai_works, etc.)
    """
    # Check if user has access to this day
    if day > current_user.current_day:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Complete Day {current_user.current_day} before accessing Day {day}"
        )

    result = await db.execute(
        select(Lesson).where(
            Lesson.day == day,
            Lesson.language == current_user.language
        ).order_by(Lesson.topic)
    )
    lessons = result.scalars().all()

    if not lessons:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lessons found for Day {day} in language {current_user.language}"
        )

    return list(lessons)


@router.post("/quiz/submit", response_model=QuizResult)
async def submit_quiz(
    submission: QuizSubmission,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit quiz answers for a lesson

    - Requires 5 answers (indices 0-3 for options A-D)
    - Pass threshold: 60% (3/5 correct)
    - Maximum 3 attempts per lesson
    - Marks lesson complete if passed
    """
    manager = LessonStateManager(db)

    # Verify lesson exists and user has access
    result = await db.execute(
        select(Lesson).where(Lesson.id == submission.lesson_id)
    )
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {submission.lesson_id} not found"
        )

    if lesson.day > current_user.current_day:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Complete Day {current_user.current_day} first"
        )

    # Check attempt count
    attempts_result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.lesson_id == submission.lesson_id
        )
    )
    previous_attempts = attempts_result.scalars().all()

    if len(previous_attempts) >= 3:
        # Check if already passed
        passed_attempt = any(
            QuizAttempt.is_passing_score(attempt.score)
            for attempt in previous_attempts
        )

        if passed_attempt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You've already passed this quiz"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 3 attempts reached for this lesson"
            )

    # Record quiz attempt
    quiz_result = await manager.record_quiz_attempt(
        user_id=current_user.id,
        lesson_id=submission.lesson_id,
        user_answers=submission.user_answers
    )

    # Generate feedback message
    if quiz_result.passed:
        if quiz_result.score == 100:
            feedback = "Perfect score! Excellent work!"
        elif quiz_result.score >= 80:
            feedback = "Great job! You passed with flying colors."
        else:
            feedback = "Well done! You passed the quiz."
    else:
        attempts_remaining = 3 - quiz_result.attempts_used
        if attempts_remaining > 0:
            feedback = f"You need 60% to pass. {attempts_remaining} attempt(s) remaining. Review the lesson and try again!"
        else:
            feedback = "Maximum attempts reached. Please contact support for help."

    # Check if lesson is complete (passed quiz)
    progress_result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == current_user.id,
            LessonProgress.lesson_id == submission.lesson_id
        )
    )
    progress = progress_result.scalar_one_or_none()
    lesson_completed = progress.is_completed if progress else False

    return QuizResult(
        lesson_id=submission.lesson_id,
        score=quiz_result.score,
        correct_count=quiz_result.correct_count,
        total_questions=5,
        passed=quiz_result.passed,
        attempts_used=quiz_result.attempt_number,
        attempts_remaining=max(3 - quiz_result.attempt_number, 0),
        lesson_completed=lesson_completed,
        feedback=feedback
    )


@router.get("/progress/day/{day}", response_model=DayProgressResponse)
async def get_day_progress(
    day: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get progress for a specific day

    Returns:
    - Lessons completed
    - Average score
    - Whether day is complete
    """
    from sqlalchemy import func, and_

    # Get lessons for this day
    lessons_result = await db.execute(
        select(Lesson).where(
            Lesson.day == day,
            Lesson.language == current_user.language
        )
    )
    lessons = lessons_result.scalars().all()
    lesson_ids = [lesson.id for lesson in lessons]

    # Count completed lessons
    completed_result = await db.execute(
        select(func.count(LessonProgress.id)).where(
            and_(
                LessonProgress.user_id == current_user.id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.is_completed == True
            )
        )
    )
    lessons_completed = completed_result.scalar() or 0

    # Calculate average score for this day
    avg_score_result = await db.execute(
        select(func.avg(LessonProgress.best_score)).where(
            and_(
                LessonProgress.user_id == current_user.id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.is_completed == True
            )
        )
    )
    avg_score = avg_score_result.scalar()

    # Get completion date (latest lesson completion for this day)
    completion_date_result = await db.execute(
        select(LessonProgress.completed_at).where(
            and_(
                LessonProgress.user_id == current_user.id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.is_completed == True
            )
        ).order_by(LessonProgress.completed_at.desc()).limit(1)
    )
    completion_date = completion_date_result.scalar_one_or_none()

    is_complete = lessons_completed == 5  # All 5 topics complete

    return DayProgressResponse(
        day=day,
        lessons_completed=lessons_completed,
        total_lessons=5,
        average_score=round(avg_score, 2) if avg_score else None,
        is_complete=is_complete,
        completion_date=completion_date
    )


@router.get("/progress/all", response_model=List[LessonProgressResponse])
async def get_all_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all lesson progress for current user

    Returns progress records for all lessons attempted
    """
    result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == current_user.id
        ).order_by(LessonProgress.last_attempt_date.desc())
    )
    progress_records = result.scalars().all()

    return list(progress_records)
