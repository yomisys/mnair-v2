"""
Integration tests for USSD conversation flow
Tests complete menu navigation and lesson delivery for feature phones
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import json

from app.models.user import User, Language
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.channels.ussd import (
    USSDHandler,
    USSDResponse,
    ContentChunker,
    USSDMenuState,
    USSDSessionManager
)
from app.config import Settings


# Mock Redis client for testing
class MockRedis:
    """Mock Redis client for testing"""

    def __init__(self):
        self.data = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def setex(self, key: str, timeout: int, value: str):
        self.data[key] = value

    async def delete(self, key: str):
        self.data.pop(key, None)

    async def close(self):
        pass


def test_ussd_response_builders():
    """Test USSD response formatters"""
    # Test CON response
    con_msg = USSDResponse.con("Choose option:\n1. Yes\n2. No")
    assert con_msg.startswith("CON ")
    assert "Choose option" in con_msg

    # Test END response
    end_msg = USSDResponse.end("Thank you!")
    assert end_msg.startswith("END ")
    assert "Thank you" in end_msg


def test_content_chunker_short_text():
    """Test chunking short text (< 160 chars)"""
    short_text = "This is a short lesson about AI."
    chunks = ContentChunker.chunk_text(short_text)

    assert len(chunks) == 1
    assert chunks[0] == short_text


def test_content_chunker_long_text():
    """Test chunking long text into multiple screens"""
    long_text = (
        "AI is Artificial Intelligence. It is a technology that allows computers to learn "
        "and solve problems like humans. In Nigeria, AI can help solve many challenges. "
        "For example, AI can predict traffic patterns in Lagos and suggest better routes. "
        "It can help farmers know the best time to plant crops. AI can also detect diseases "
        "from medical images, helping doctors save lives faster."
    )

    chunks = ContentChunker.chunk_text(long_text, max_chars=160)

    # Should create multiple chunks
    assert len(chunks) > 1

    # Each chunk should be <= 160 chars
    for chunk in chunks:
        assert len(chunk) <= 160

    # Combined should equal original (minus whitespace)
    combined = " ".join(chunks)
    assert combined.replace("  ", " ") == " ".join(long_text.split())


def test_content_chunker_format_lesson():
    """Test lesson chunk formatting with navigation"""
    chunk = "This is lesson content about AI technology."

    # First chunk
    formatted = ContentChunker.format_lesson_chunk(chunk, 0, 3)
    assert "[1/3]" in formatted
    assert "1. Continue" in formatted
    assert "0. Main Menu" in formatted

    # Last chunk
    formatted_last = ContentChunker.format_lesson_chunk(chunk, 2, 3)
    assert "[3/3]" in formatted_last
    assert "1. Take Quiz" in formatted_last


@pytest.mark.asyncio
async def test_session_manager():
    """Test Redis session management"""
    redis_mock = MockRedis()
    session_mgr = USSDSessionManager(redis_mock)

    session_id = "test_session_123"
    session_data = {
        "phone_number": "+2348012345678",
        "state": USSDMenuState.MAIN_MENU,
        "data": {"test": "value"}
    }

    # Save session
    await session_mgr.save_session(session_id, session_data)

    # Retrieve session
    retrieved = await session_mgr.get_session(session_id)
    assert retrieved is not None
    assert retrieved["phone_number"] == "+2348012345678"
    assert retrieved["state"] == USSDMenuState.MAIN_MENU

    # Clear session
    await session_mgr.clear_session(session_id)
    cleared = await session_mgr.get_session(session_id)
    assert cleared is None


@pytest.mark.asyncio
async def test_ussd_handler_main_menu(test_db):
    """Test main menu display"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Test showing main menu
    menu = await handler.show_main_menu()
    assert menu.startswith("CON ")
    assert "Make Nigeria AI Ready" in menu
    assert "1. Start Learning" in menu
    assert "2. My Progress" in menu
    assert "3. Get Certificate" in menu


@pytest.mark.asyncio
async def test_ussd_handler_language_selection(test_db):
    """Test language selection menu"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Show language menu
    lang_menu = await handler.show_language_menu()
    assert "CON " in lang_menu
    assert "1. English" in lang_menu
    assert "2. Pidgin" in lang_menu
    assert "3. Hausa" in lang_menu
    assert "4. Yoruba" in lang_menu
    assert "5. Igbo" in lang_menu


@pytest.mark.asyncio
async def test_ussd_new_session_flow(test_db):
    """Test complete new session flow"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    phone = "+2348012345678"
    session_id = "session_001"

    # First request (empty text) should show main menu
    response = await handler.handle_request(session_id, phone, "")
    assert response.startswith("CON ")
    assert "Make Nigeria AI Ready" in response


@pytest.mark.asyncio
async def test_ussd_start_learning_flow(test_db):
    """Test starting learning journey"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    phone = "+2348012345679"
    session_id = "session_002"

    # Initialize session
    await handler.handle_request(session_id, phone, "")

    # Select "Start Learning" (option 1)
    response = await handler.handle_request(session_id, phone, "1")

    # Should show language selection
    assert "CON " in response
    assert "Choose your language" in response


@pytest.mark.asyncio
async def test_ussd_language_selection_flow(test_db):
    """Test language selection and lesson delivery"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create a test lesson
    lesson = Lesson(
        lesson_id="day1_test_ussd_en",
        day=1,
        topic="test_topic",
        language="en",
        title="Test Lesson",
        content="This is a test lesson about AI. It teaches you the basics.",
        word_count=12,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
    )
    test_db.add(lesson)
    await test_db.commit()

    phone = "+2348012345680"
    session_id = "session_003"

    # Start session
    await handler.handle_request(session_id, phone, "")

    # Select Start Learning
    await handler.handle_request(session_id, phone, "1")

    # Select English (option 1)
    response = await handler.handle_request(session_id, phone, "1*1")

    # Should show first lesson
    assert "CON " in response
    assert "Test Lesson" in response or "test lesson" in response.lower()


@pytest.mark.asyncio
async def test_ussd_lesson_navigation(test_db):
    """Test navigating through lesson chunks"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create lesson with long content that will chunk
    long_content = " ".join(["This is sentence number " + str(i) + "." for i in range(20)])
    lesson = Lesson(
        lesson_id="day1_long_ussd_en",
        day=1,
        topic="long_lesson",
        language="en",
        title="Long Lesson",
        content=long_content,
        word_count=60,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
    )
    test_db.add(lesson)
    await test_db.commit()

    phone = "+2348012345681"
    session_id = "session_004"

    # Start and select language
    await handler.handle_request(session_id, phone, "")
    await handler.handle_request(session_id, phone, "1")
    await handler.handle_request(session_id, phone, "1*1")

    # Get session to check chunks
    session = await handler.session_mgr.get_session(session_id)
    chunks = session.get("data", {}).get("lesson_chunks", [])

    if len(chunks) > 1:
        # Navigate to next chunk (option 1 = Continue)
        response = await handler.handle_request(session_id, phone, "1*1*1")
        assert "CON " in response
        # Should show chunk 2
        assert "[2/" in response or "Continue" in response


@pytest.mark.asyncio
async def test_ussd_quiz_flow(test_db):
    """Test taking quiz via USSD"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create lesson
    lesson = Lesson(
        lesson_id="day1_quiz_test_en",
        day=1,
        topic="quiz_test",
        language="en",
        title="Quiz Test",
        content="Short lesson for quiz testing.",
        word_count=5,
        quiz=[
            {"question": "What is AI?", "options": ["Artificial Intelligence", "B", "C", "D"], "correct": 0},
            {"question": "Question 2", "options": ["A", "B", "C", "D"], "correct": 1},
            {"question": "Question 3", "options": ["A", "B", "C", "D"], "correct": 2},
            {"question": "Question 4", "options": ["A", "B", "C", "D"], "correct": 3},
            {"question": "Question 5", "options": ["A", "B", "C", "D"], "correct": 0},
        ]
    )
    test_db.add(lesson)
    await test_db.commit()

    phone = "+2348012345682"
    session_id = "session_005"

    # Setup: Start learning, select language, view lesson
    await handler.handle_request(session_id, phone, "")
    await handler.handle_request(session_id, phone, "1")
    await handler.handle_request(session_id, phone, "1*1")

    # Start quiz (option 1 on last chunk)
    response = await handler.handle_request(session_id, phone, "1*1*1")

    # Should show first quiz question
    assert "CON " in response
    assert "Question 1/5" in response
    assert "What is AI" in response

    # Answer question 1 correctly (option 1)
    response = await handler.handle_request(session_id, phone, "1*1*1*1")
    assert "Question 2/5" in response

    # Answer remaining questions
    await handler.handle_request(session_id, phone, "1*1*1*1*2")  # Q2
    await handler.handle_request(session_id, phone, "1*1*1*1*2*3")  # Q3
    await handler.handle_request(session_id, phone, "1*1*1*1*2*3*4")  # Q4
    response = await handler.handle_request(session_id, phone, "1*1*1*1*2*3*4*1")  # Q5

    # Should show quiz result
    assert "CON " in response
    assert "PASSED" in response or "Score" in response


@pytest.mark.asyncio
async def test_ussd_progress_display(test_db):
    """Test progress display"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create user with some progress
    user = User(
        phone_number="+2348012345683",
        name="Progress Test User",
        language=Language.ENGLISH,
        current_day=2,
        completed_days=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create and complete some lessons
    for i in range(5):
        lesson = Lesson(
            lesson_id=f"day1_progress_{i}_en",
            day=1,
            topic=f"topic_{i}",
            language="en",
            title=f"Lesson {i}",
            content="Test content",
            word_count=2,
            quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
        )
        test_db.add(lesson)
        await test_db.flush()

        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=100.0
        )
        test_db.add(progress)

    await test_db.commit()

    session_id = "session_006"

    # Start session
    await handler.handle_request(session_id, user.phone_number, "")

    # Select "My Progress" (option 2)
    response = await handler.handle_request(session_id, user.phone_number, "2")

    # Should show progress
    assert "END " in response  # Progress ends session
    assert "Progress" in response or "Day" in response
    assert "5" in response  # 5 lessons completed


@pytest.mark.asyncio
async def test_ussd_certificate_not_ready(test_db):
    """Test certificate request when not completed"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    phone = "+2348012345684"
    session_id = "session_007"

    # Start session
    await handler.handle_request(session_id, phone, "")

    # Select "Get Certificate" (option 3)
    response = await handler.handle_request(session_id, phone, "3")

    # Should show not ready message
    assert "END " in response
    assert "Complete all 7 days" in response or "Day" in response


@pytest.mark.asyncio
async def test_ussd_return_to_main_menu(test_db):
    """Test navigation back to main menu"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create lesson
    lesson = Lesson(
        lesson_id="day1_nav_test_en",
        day=1,
        topic="nav_test",
        language="en",
        title="Navigation Test",
        content="Test lesson for navigation.",
        word_count=4,
        quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
    )
    test_db.add(lesson)
    await test_db.commit()

    phone = "+2348012345685"
    session_id = "session_008"

    # Start learning flow
    await handler.handle_request(session_id, phone, "")
    await handler.handle_request(session_id, phone, "1")
    await handler.handle_request(session_id, phone, "1*1")

    # Press 0 to return to main menu
    response = await handler.handle_request(session_id, phone, "1*1*0")

    # Should show main menu
    assert "CON " in response
    assert "Make Nigeria AI Ready" in response
    assert "1. Start Learning" in response


@pytest.mark.asyncio
async def test_ussd_invalid_input(test_db):
    """Test handling of invalid menu choices"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    phone = "+2348012345686"
    session_id = "session_009"

    # Start session
    await handler.handle_request(session_id, phone, "")

    # Enter invalid choice (99)
    response = await handler.handle_request(session_id, phone, "99")

    # Should show error and end session
    assert "END " in response
    assert "Invalid" in response or "try again" in response.lower()


@pytest.mark.asyncio
async def test_ussd_day_completion(test_db):
    """Test day completion flow"""
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    # Create user who completed Day 1
    user = User(
        phone_number="+2348012345687",
        name="Day Complete User",
        language=Language.ENGLISH,
        current_day=1,
        completed_days=0,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create and complete all 5 Day 1 lessons
    for topic in ["ai_ethics", "ai_in_nigeria", "ai_tools", "how_ai_works", "what_is_ai"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Lesson: {topic}",
            content="Test content for completed day",
            word_count=5,
            quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
        )
        test_db.add(lesson)
        await test_db.flush()

        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=100.0
        )
        test_db.add(progress)

    # Create Day 2 lessons
    for topic in ["ai_ethics", "ai_in_nigeria"]:
        lesson = Lesson(
            lesson_id=f"day2_{topic}_en",
            day=2,
            topic=topic,
            language="en",
            title=f"Day 2: {topic}",
            content="Day 2 content",
            word_count=3,
            quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
        )
        test_db.add(lesson)

    await test_db.commit()

    session_id = "session_010"

    # Manually set session to show day completion
    session = {
        "phone_number": user.phone_number,
        "state": USSDMenuState.DAY_COMPLETE,
        "user_id": user.id,
        "data": {}
    }
    await handler.session_mgr.save_session(session_id, session)

    # Request with choice "1" to advance
    response = await handler.handle_request(session_id, user.phone_number, "1")

    # Should advance to Day 2
    assert "CON " in response
    # User should be on Day 2 now
    await test_db.refresh(user)
    assert user.current_day == 2


@pytest.mark.asyncio
async def test_ussd_day_seven_completion_sets_completed_days_to_seven(test_db):
    """
    Regression test for "completed Day 7, never received certificate" (USSD).

    Before the fix, completed_days only incremented inside advance_to_next_day,
    which is never reached on Day 7 (there's no Day 8 to advance to). That made
    completed_days permanently stuck at 6, so the certificate menu's own check
    (`current_day >= 7 and completed_days >= 7`) could never pass — a USSD
    finisher was told "keep going" forever on a day they'd already finished.
    """
    settings = Settings()
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    user = User(
        phone_number="+2348012345698",
        name="USSD Day 7 Finisher",
        language=Language.ENGLISH,
        current_day=7,
        completed_days=6,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    for topic in ["ai_ethics", "ai_in_nigeria", "ai_tools", "how_ai_works", "what_is_ai"]:
        lesson = Lesson(
            lesson_id=f"day7_{topic}_en",
            day=7,
            topic=topic,
            language="en",
            title=f"Day 7: {topic}",
            content="Test content",
            word_count=5,
            quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
        )
        test_db.add(lesson)
        await test_db.flush()

        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=100.0
        )
        test_db.add(progress)

    await test_db.commit()

    session = {
        "phone_number": user.phone_number,
        "state": USSDMenuState.LESSON_DISPLAY,
        "user_id": user.id,
        "data": {}
    }

    # All Day 7 lessons already complete -> get_next_lesson returns None ->
    # the day-complete branch fires, same path a real finisher hits
    await handler.deliver_next_lesson(user, session)

    await test_db.refresh(user)
    assert user.current_day == 7
    assert user.completed_days == 7


@pytest.mark.asyncio
async def test_ussd_certificate_ready_uses_real_domain(test_db):
    """The USSD certificate-ready message must point at mnair.ng, not the
    never-deployed mnair.gov.ng — a learner who reaches this branch (now
    reachable thanks to the completed_days fix) still hit a dead link."""
    settings = Settings(FRONTEND_URL="https://mnair.ng")
    redis_mock = MockRedis()
    handler = USSDHandler(test_db, redis_mock, settings)

    user = User(
        phone_number="+2348012345697",
        name="Finisher",
        language=Language.ENGLISH,
        current_day=7,
        completed_days=7,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.commit()

    session_id = "session_cert_ready"
    await handler.handle_request(session_id, user.phone_number, "")
    response = await handler.handle_request(session_id, user.phone_number, "3")

    assert "mnair.ng" in response
    assert "mnair.gov.ng" not in response
