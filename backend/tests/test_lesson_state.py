"""
Unit tests for LessonStateManager service
Tests quiz scoring, progress tracking, and day completion logic
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Language
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt
from app.services.lesson_state import LessonStateManager, QuizResult, ProgressSummary


@pytest.mark.asyncio
async def test_get_next_lesson_first_day(test_db: AsyncSession):
    """Test getting the first lesson for a new user"""
    # Create user on day 1
    user = User(
        phone_number="+2348012345678",
        name="Test User 78",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create 5 lessons for day 1
    for i, topic in enumerate(["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]):
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content for lesson",
            word_count=4,
            quiz=[
                {
                    "question": f"Question {j+1}",
                    "options": ["A", "B", "C", "D"],
                    "correct": 0
                }
                for j in range(5)
            ]
        )
        test_db.add(lesson)

    await test_db.commit()

    # Get next lesson (should be first one)
    manager = LessonStateManager(test_db)
    next_lesson = await manager.get_next_lesson(user.id, "en")

    assert next_lesson is not None
    assert next_lesson.topic == "ai_ethics"  # First alphabetically
    assert next_lesson.day == 1


@pytest.mark.asyncio
async def test_get_next_lesson_with_progress(test_db: AsyncSession):
    """Test getting next lesson when some are already completed"""
    # Create user
    user = User(
        phone_number="+2348012345679",
        name="Test User 79",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create 5 lessons
    lessons = []
    for i, topic in enumerate(["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]):
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)
        lessons.append(lesson)

    await test_db.flush()

    # Mark first two lessons as completed (alphabetically: ai_ethics and ai_in_nigeria)
    for lesson in lessons:
        if lesson.topic not in ["ai_ethics", "ai_in_nigeria"]:
            continue
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=80.0
        )
        test_db.add(progress)

    await test_db.commit()

    # Get next lesson (should be third one)
    manager = LessonStateManager(test_db)
    next_lesson = await manager.get_next_lesson(user.id, "en")

    assert next_lesson is not None
    assert next_lesson.topic == "ai_tools"  # After completing first 2


@pytest.mark.asyncio
async def test_get_next_lesson_all_complete(test_db: AsyncSession):
    """Test when all lessons for the day are complete"""
    # Create user
    user = User(
        phone_number="+2348012345680",
        name="Test User 80",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create 5 lessons
    for topic in ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)
        await test_db.flush()

        # Mark as completed
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=80.0
        )
        test_db.add(progress)

    await test_db.commit()

    # Get next lesson (should be None)
    manager = LessonStateManager(test_db)
    next_lesson = await manager.get_next_lesson(user.id, "en")

    assert next_lesson is None


@pytest.mark.asyncio
async def test_record_quiz_attempt_passing(test_db: AsyncSession):
    """Test recording a passing quiz attempt (60%+)"""
    # Create user and lesson
    user = User(
        phone_number="+2348012345681",
        name="Test User 81",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_what_is_ai_en",
        day=1,
        topic="what_is_ai",
        language="en",
        title="What is AI?",
        content="Test content",
            word_count=2,
        quiz=[
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": 3},
            {"question": "Q5", "options": ["A", "B", "C", "D"], "correct": 0},
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    # Record quiz attempt with 4/5 correct (80%)
    manager = LessonStateManager(test_db)
    user_answers = [0, 1, 2, 3, 1]  # 4 correct, 1 wrong
    result = await manager.record_quiz_attempt(user.id, lesson.id, user_answers)

    # Verify result
    assert isinstance(result, QuizResult)
    assert result.score == 80.0
    assert result.correct_count == 4
    assert result.total_questions == 5
    assert result.passed is True
    assert result.attempt_number == 1
    assert result.can_retry is False  # Can't retry because passed

    # Verify database records
    result = await test_db.execute(
        select(QuizAttempt).where(QuizAttempt.user_id == user.id)
    )
    attempt = result.scalar_one()
    assert attempt.score == 80.0
    assert attempt.passed is True

    result = await test_db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user.id)
    )
    progress = result.scalar_one()
    assert progress.is_completed is True
    assert progress.quiz_score == 80.0


@pytest.mark.asyncio
async def test_record_quiz_attempt_failing(test_db: AsyncSession):
    """Test recording a failing quiz attempt (below 60%)"""
    # Create user and lesson
    user = User(
        phone_number="+2348012345682",
        name="Test User 82",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_how_ai_works_en",
        day=1,
        topic="how_ai_works",
        language="en",
        title="How AI Works",
        content="Test content",
            word_count=2,
        quiz=[
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": 3},
            {"question": "Q5", "options": ["A", "B", "C", "D"], "correct": 0},
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    # Record quiz attempt with 2/5 correct (40%)
    manager = LessonStateManager(test_db)
    user_answers = [0, 0, 0, 0, 0]  # Only 2 correct
    result = await manager.record_quiz_attempt(user.id, lesson.id, user_answers)

    # Verify result
    assert result.score == 40.0
    assert result.correct_count == 2
    assert result.passed is False
    assert result.attempt_number == 1
    assert result.can_retry is True  # Can retry because failed

    # Verify database - lesson not completed
    result = await test_db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user.id)
    )
    progress = result.scalar_one()
    assert progress.is_completed is False
    assert progress.quiz_attempts_count == 1


@pytest.mark.asyncio
async def test_quiz_attempt_max_retries(test_db: AsyncSession):
    """Test that quiz allows max 3 attempts"""
    # Create user and lesson
    user = User(
        phone_number="+2348012345683",
        name="Test User 83",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_ai_in_nigeria_en",
        day=1,
        topic="ai_in_nigeria",
        language="en",
        title="AI in Nigeria",
        content="Test content",
            word_count=2,
        quiz=[
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": 3},
            {"question": "Q5", "options": ["A", "B", "C", "D"], "correct": 0},
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    manager = LessonStateManager(test_db)
    user_answers = [1, 1, 1, 1, 1]  # All wrong (0%)

    # Attempt 1
    result1 = await manager.record_quiz_attempt(user.id, lesson.id, user_answers)
    assert result1.attempt_number == 1
    assert result1.can_retry is True

    # Attempt 2
    result2 = await manager.record_quiz_attempt(user.id, lesson.id, user_answers)
    assert result2.attempt_number == 2
    assert result2.can_retry is True

    # Attempt 3
    result3 = await manager.record_quiz_attempt(user.id, lesson.id, user_answers)
    assert result3.attempt_number == 3
    assert result3.can_retry is False  # No more retries


@pytest.mark.asyncio
async def test_is_day_complete(test_db: AsyncSession):
    """Test day completion check"""
    # Create user
    user = User(
        phone_number="+2348012345684",
        name="Test User 84",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create 5 lessons for day 1
    for topic in ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)

    await test_db.commit()

    manager = LessonStateManager(test_db)

    # Initially not complete
    is_complete = await manager.is_day_complete(user.id, 1)
    assert is_complete is False

    # Complete 4 lessons
    result = await test_db.execute(select(Lesson).where(Lesson.day == 1))
    lessons = list(result.scalars().all())

    for lesson in lessons[:4]:
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=80.0
        )
        test_db.add(progress)

    await test_db.commit()

    # Still not complete (4/5)
    is_complete = await manager.is_day_complete(user.id, 1)
    assert is_complete is False

    # Complete 5th lesson
    progress = LessonProgress(
        user_id=user.id,
        lesson_id=lessons[4].id,
        is_started=True,
        is_completed=True,
        quiz_score=80.0
    )
    test_db.add(progress)
    await test_db.commit()

    # Now complete
    is_complete = await manager.is_day_complete(user.id, 1)
    assert is_complete is True


@pytest.mark.asyncio
async def test_advance_to_next_day(test_db: AsyncSession):
    """Test advancing user to next day"""
    # Create user on day 1
    user = User(
        phone_number="+2348012345685",
        name="Test User 85",
        language=Language.ENGLISH,
        current_day=1,
        completed_days=0,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create and complete all 5 lessons
    for topic in ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)
        await test_db.flush()

        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=80.0
        )
        test_db.add(progress)

    await test_db.commit()

    # Advance to next day
    manager = LessonStateManager(test_db)
    advanced = await manager.advance_to_next_day(user.id)

    assert advanced is True

    # Verify user updated
    await test_db.refresh(user)
    assert user.current_day == 2
    assert user.completed_days == 1


@pytest.mark.asyncio
async def test_advance_day_not_complete(test_db: AsyncSession):
    """Test that advancing fails if day not complete"""
    # Create user
    user = User(
        phone_number="+2348012345686",
        name="Test User 86",
        language=Language.ENGLISH,
        current_day=1,
        completed_days=0,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create lessons but don't complete them
    for topic in ["what_is_ai", "how_ai_works"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)

    await test_db.commit()

    # Try to advance (should fail)
    manager = LessonStateManager(test_db)
    advanced = await manager.advance_to_next_day(user.id)

    assert advanced is False

    # Verify user not updated
    await test_db.refresh(user)
    assert user.current_day == 1
    assert user.completed_days == 0


@pytest.mark.asyncio
async def test_get_user_progress(test_db: AsyncSession):
    """Test getting user progress summary"""
    # Create user
    user = User(
        phone_number="+2348012345687",
        name="Test User 87",
        language=Language.ENGLISH,
        current_day=2,
        completed_days=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create day 1 lessons (all completed)
    for topic in ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)
        await test_db.flush()

        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=80.0
        )
        test_db.add(progress)

    # Create day 2 lessons (2 completed)
    for i, topic in enumerate(["what_is_ai", "how_ai_works", "ai_in_nigeria"]):
        lesson = Lesson(
            lesson_id=f"day2_{topic}_en",
            day=2,
            topic=topic,
            language="en",
            title=f"Day 2: {topic}",
            content="Test content",
            word_count=2,
            quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
        )
        test_db.add(lesson)
        await test_db.flush()

        if i < 2:  # Complete first 2
            progress = LessonProgress(
                user_id=user.id,
                lesson_id=lesson.id,
                is_started=True,
                is_completed=True,
                quiz_score=80.0
            )
            test_db.add(progress)

    await test_db.commit()

    # Get progress
    manager = LessonStateManager(test_db)
    summary = await manager.get_user_progress(user.id)

    assert summary is not None
    assert isinstance(summary, ProgressSummary)
    assert summary.user_id == user.id
    assert summary.current_day == 2
    assert summary.lessons_completed == 7  # 5 from day 1 + 2 from day 2
    assert summary.total_lessons == 35  # 7 days * 5 lessons
    assert summary.completion_percentage == 20.0  # 7/35 * 100
    assert summary.current_day_progress == 2  # 2 lessons on day 2
    assert summary.lessons_per_day == 5


@pytest.mark.asyncio
async def test_get_quiz_attempts(test_db: AsyncSession):
    """Test retrieving all quiz attempts for a lesson"""
    # Create user and lesson
    user = User(
        phone_number="+2348012345688",
        name="Test User 88",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_ai_tools_en",
        day=1,
        topic="ai_tools",
        language="en",
        title="AI Tools",
        content="Test content",
            word_count=2,
        quiz=[
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct": 3},
            {"question": "Q5", "options": ["A", "B", "C", "D"], "correct": 0},
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    manager = LessonStateManager(test_db)

    # Make 3 attempts
    await manager.record_quiz_attempt(user.id, lesson.id, [1, 1, 1, 1, 1])  # Fail
    await manager.record_quiz_attempt(user.id, lesson.id, [0, 1, 1, 1, 1])  # Fail
    await manager.record_quiz_attempt(user.id, lesson.id, [0, 1, 2, 3, 0])  # Pass

    # Get all attempts
    attempts = await manager.get_quiz_attempts(user.id, lesson.id)

    assert len(attempts) == 3
    assert attempts[0].attempt_number == 1
    assert attempts[0].score == 20.0
    assert attempts[1].attempt_number == 2
    assert attempts[1].score == 40.0
    assert attempts[2].attempt_number == 3
    assert attempts[2].score == 100.0
    assert attempts[2].passed is True


@pytest.mark.asyncio
async def test_complete_lesson(test_db: AsyncSession):
    """Test marking a lesson as viewed/started"""
    # Create user and lesson
    user = User(
        phone_number="+2348012345689",
        name="Test User 89",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_ai_ethics_en",
        day=1,
        topic="ai_ethics",
        language="en",
        title="AI Ethics",
        content="Test content",
            word_count=2,
        quiz=[{"question": f"Q{j}", "options": ["A", "B", "C", "D"], "correct": 0} for j in range(5)]
    )
    test_db.add(lesson)
    await test_db.commit()

    manager = LessonStateManager(test_db)

    # Mark lesson as started
    success = await manager.complete_lesson(user.id, lesson.id)
    assert success is True

    # Verify progress record created
    result = await test_db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.lesson_id == lesson.id
        )
    )
    progress = result.scalar_one()
    assert progress.is_started is True
    assert progress.is_completed is False


@pytest.mark.asyncio
async def test_quiz_validation_error(test_db: AsyncSession):
    """Test that invalid quiz structure raises error"""
    # Create user and lesson with invalid quiz
    user = User(
        phone_number="+2348012345690",
        name="Test User 90",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)

    lesson = Lesson(
        lesson_id="day1_invalid_quiz",
        day=1,
        topic="test",
        language="en",
        title="Test",
        content="Test content",
            word_count=2,
        quiz=[
            {"question": "Q1", "options": ["A", "B"], "correct": 0},  # Only 2 options (invalid)
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    manager = LessonStateManager(test_db)

    # Should raise ValueError
    with pytest.raises(ValueError, match="invalid quiz structure"):
        await manager.record_quiz_attempt(user.id, lesson.id, [0])
