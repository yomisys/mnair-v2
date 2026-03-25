"""
Integration tests for WhatsApp conversation flow
Tests complete Day 1-7 simulation with state management
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.user import User, Language
from app.models.lesson import Lesson
from app.models.conversation import Conversation, ConversationState
from app.models.lesson_progress import LessonProgress
from app.channels.whatsapp import WhatsAppWebhookHandler, WhatsAppMessageBuilder
from app.config import Settings


@pytest.mark.asyncio
async def test_message_builder_welcome(test_db):
    """Test welcome message builder"""
    builder = WhatsAppMessageBuilder()

    # Without name
    msg = builder.build_welcome_message()
    assert "messaging_product" in msg
    assert "whatsapp" in msg["messaging_product"]
    assert "Welcome to Make Nigeria AI Ready" in msg["text"]["body"]

    # With name
    msg = builder.build_welcome_message("Chidi")
    assert "Hello Chidi!" in msg["text"]["body"]


@pytest.mark.asyncio
async def test_message_builder_language_selector(test_db):
    """Test language selector message"""
    builder = WhatsAppMessageBuilder()

    msg = builder.build_language_selector_list()
    assert msg["type"] == "interactive"
    assert msg["interactive"]["type"] == "list"
    assert len(msg["interactive"]["action"]["sections"][0]["rows"]) == 5

    # Check all languages present
    rows = msg["interactive"]["action"]["sections"][0]["rows"]
    lang_ids = [row["id"] for row in rows]
    assert "lang_en" in lang_ids
    assert "lang_pid" in lang_ids
    assert "lang_ha" in lang_ids
    assert "lang_yo" in lang_ids
    assert "lang_ig" in lang_ids


@pytest.mark.asyncio
async def test_message_builder_lesson_message(test_db):
    """Test lesson message builder"""
    builder = WhatsAppMessageBuilder()

    lesson = Lesson(
        lesson_id="test_lesson",
        day=1,
        topic="what_is_ai",
        language="en",
        title="What is AI?",
        content="AI is a technology that helps computers learn and solve problems.",
        word_count=12,
        quiz=[{"question": "Q1", "options": ["A", "B", "C", "D"], "correct": 0}] * 5
    )

    msg = builder.build_lesson_message(lesson, 1, 5)
    assert "Day 1 - Lesson 1/5" in msg["text"]["body"]
    assert "What is AI?" in msg["text"]["body"]
    assert "Reply *QUIZ* to start" in msg["text"]["body"]


@pytest.mark.asyncio
async def test_message_builder_quiz_message(test_db):
    """Test quiz question message builder"""
    builder = WhatsAppMessageBuilder()

    lesson = Lesson(
        lesson_id="test_lesson",
        day=1,
        topic="what_is_ai",
        language="en",
        title="What is AI?",
        content="Test content",
        word_count=2,
        quiz=[
            {
                "question": "What does AI stand for?",
                "options": ["Artificial Intelligence", "Automated Internet", "Advanced Info", "None"],
                "correct": 0
            }
        ] * 5
    )

    msg = builder.build_quiz_message(lesson, 0)
    assert msg["type"] == "interactive"
    assert "Question 1/5" in msg["interactive"]["body"]["text"]
    assert "What does AI stand for?" in msg["interactive"]["body"]["text"]
    assert len(msg["interactive"]["action"]["sections"][0]["rows"]) == 4


@pytest.mark.asyncio
async def test_message_builder_quiz_result_passed(test_db):
    """Test quiz result message for passing score"""
    builder = WhatsAppMessageBuilder()

    msg = builder.build_quiz_result_message(80.0, True, 1, False)
    assert "Congratulations" in msg["text"]["body"]
    assert "80%" in msg["text"]["body"]
    assert "Congratulations" in msg["text"]["body"]


@pytest.mark.asyncio
async def test_message_builder_quiz_result_failed(test_db):
    """Test quiz result message for failing score"""
    builder = WhatsAppMessageBuilder()

    # Failed with retry available
    msg = builder.build_quiz_result_message(40.0, False, 1, True)
    assert "40%" in msg["text"]["body"]
    assert "RETRY" in msg["text"]["body"]

    # Failed without retry
    msg = builder.build_quiz_result_message(40.0, False, 3, False)
    assert "Maximum attempts reached" in msg["text"]["body"]


@pytest.mark.asyncio
async def test_message_builder_day_complete(test_db):
    """Test day completion message"""
    builder = WhatsAppMessageBuilder()

    msg = builder.build_day_complete_message(1, 5)
    assert "DAY 1 COMPLETE" in msg["text"]["body"]
    assert "5 lessons" in msg["text"]["body"]
    assert "NEXT" in msg["text"]["body"]


@pytest.mark.asyncio
async def test_get_or_create_user(test_db):
    """Test user creation and retrieval"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Create new user
    user1 = await handler.get_or_create_user("+2348012345678", "Test User")
    assert user1.phone_number == "+2348012345678"
    assert user1.name == "Test User"
    assert user1.language == Language.ENGLISH

    # Get existing user
    user2 = await handler.get_or_create_user("+2348012345678")
    assert user1.id == user2.id


@pytest.mark.asyncio
async def test_get_or_create_conversation(test_db):
    """Test conversation creation and retrieval"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Create user first
    user = await handler.get_or_create_user("+2348012345678", "Test User")

    # Create conversation
    conv1 = await handler.get_or_create_conversation(user.id, "+2348012345678")
    assert conv1.user_id == user.id
    assert conv1.current_state == ConversationState.NEW_USER
    assert conv1.is_active is True

    # Get existing conversation
    conv2 = await handler.get_or_create_conversation(user.id, "+2348012345678")
    assert conv1.id == conv2.id


@pytest.mark.asyncio
async def test_handle_new_user_flow(test_db):
    """Test NEW_USER state handling"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Create user and conversation
    user = User(
        phone_number="+2348012345678",
        name="Test User",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345678",
        current_state=ConversationState.NEW_USER,
        is_active=True
    )
    test_db.add(conversation)
    await test_db.commit()

    # Handle new user
    await handler.handle_new_user(user, conversation)

    # Check state updated
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.AWAITING_LANGUAGE


@pytest.mark.asyncio
async def test_handle_language_selection(test_db):
    """Test language selection handling"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Setup user and conversation
    user = User(
        phone_number="+2348012345679",
        name="Test User 2",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345679",
        current_state=ConversationState.AWAITING_LANGUAGE,
        is_active=True
    )
    test_db.add(conversation)

    # Create a lesson for Day 1
    lesson = Lesson(
        lesson_id="day1_test_en",
        day=1,
        topic="test_topic",
        language="en",
        title="Test Lesson",
        content="Test content for lesson",
        word_count=4,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
    )
    test_db.add(lesson)
    await test_db.commit()

    # Select English
    await handler.handle_language_selection(user, conversation, "lang_en")

    # Check language updated
    await test_db.refresh(user)
    assert user.language == Language.ENGLISH

    # Check state moved to IN_LESSON
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.IN_LESSON


@pytest.mark.asyncio
async def test_full_lesson_flow(test_db):
    """Test complete lesson flow from start to quiz completion"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Setup user
    user = User(
        phone_number="+2348012345680",
        name="Test User 3",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create 5 lessons for Day 1
    for topic in ["ai_ethics", "ai_in_nigeria", "ai_tools", "how_ai_works", "what_is_ai"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content for lesson",
            word_count=4,
            quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
        )
        test_db.add(lesson)

    await test_db.commit()

    # Create conversation in IN_LESSON state
    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345680",
        current_state=ConversationState.IN_LESSON,
        is_active=True
    )
    test_db.add(conversation)
    await test_db.commit()

    # Deliver first lesson
    await handler.deliver_next_lesson(user, conversation)

    # Check conversation context has lesson ID
    await test_db.refresh(conversation)
    assert "current_lesson_id" in conversation.context

    # Request quiz
    await handler.handle_lesson_flow(user, conversation, "QUIZ")

    # Check state moved to AWAITING_QUIZ
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.AWAITING_QUIZ
    assert conversation.context["current_question"] == 0
    assert conversation.context["answers"] == []

    # Answer all 5 questions correctly
    for i in range(5):
        await handler.handle_quiz_response(user, conversation, f"ans_{i}_0")
        await test_db.refresh(conversation)

    # Should be back in IN_LESSON state
    assert conversation.current_state == ConversationState.IN_LESSON

    # Check lesson was marked complete
    result = await test_db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.is_completed == True
        )
    )
    progress = result.scalars().all()
    assert len(progress) == 1
    assert progress[0].quiz_score == 100.0


@pytest.mark.asyncio
async def test_day_completion_flow(test_db):
    """Test day completion and advancement"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Setup user on Day 1
    user = User(
        phone_number="+2348012345681",
        name="Test User 4",
        language=Language.ENGLISH,
        current_day=1,
        completed_days=0,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create and complete all 5 lessons
    for topic in ["ai_ethics", "ai_in_nigeria", "ai_tools", "how_ai_works", "what_is_ai"]:
        lesson = Lesson(
            lesson_id=f"day1_{topic}_en",
            day=1,
            topic=topic,
            language="en",
            title=f"Day 1: {topic}",
            content="Test content for lesson",
            word_count=4,
            quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
        )
        test_db.add(lesson)
        await test_db.flush()

        # Mark as completed
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson.id,
            is_started=True,
            is_completed=True,
            quiz_score=100.0
        )
        test_db.add(progress)

    await test_db.commit()

    # Create conversation
    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345681",
        current_state=ConversationState.IN_LESSON,
        is_active=True
    )
    test_db.add(conversation)
    await test_db.commit()

    # Try to get next lesson (should trigger day completion)
    await handler.deliver_next_lesson(user, conversation)

    # Should be in DAY_COMPLETE state
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.DAY_COMPLETE

    # Create Day 2 lessons
    for topic in ["ai_ethics", "ai_in_nigeria"]:
        lesson = Lesson(
            lesson_id=f"day2_{topic}_en",
            day=2,
            topic=topic,
            language="en",
            title=f"Day 2: {topic}",
            content="Test content for lesson",
            word_count=4,
            quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
        )
        test_db.add(lesson)
    await test_db.commit()

    # Advance to next day
    await handler.handle_day_complete(user, conversation, "NEXT")

    # Check user advanced to Day 2
    await test_db.refresh(user)
    assert user.current_day == 2
    assert user.completed_days == 1

    # Check conversation state
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.IN_LESSON


@pytest.mark.asyncio
async def test_quiz_retry_flow(test_db):
    """Test quiz retry logic when user fails"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Setup user
    user = User(
        phone_number="+2348012345682",
        name="Test User 5",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    # Create lesson
    lesson = Lesson(
        lesson_id="day1_retry_test_en",
        day=1,
        topic="retry_test",
        language="en",
        title="Retry Test",
        content="Test content",
        word_count=2,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)]
    )
    test_db.add(lesson)
    await test_db.flush()

    # Create conversation in AWAITING_QUIZ state
    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345682",
        current_state=ConversationState.AWAITING_QUIZ,
        is_active=True,
        context={
            "current_lesson_id": lesson.id,
            "current_question": 0,
            "answers": []
        }
    )
    test_db.add(conversation)
    await test_db.commit()

    # Answer all questions incorrectly (all wrong)
    for i in range(5):
        await handler.handle_quiz_response(user, conversation, f"ans_{i}_3")  # All select option 3
        await test_db.refresh(conversation)

    # Should be back in IN_LESSON state (failed)
    assert conversation.current_state == ConversationState.IN_LESSON

    # Check quiz attempt recorded with failing score
    result = await test_db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.lesson_id == lesson.id
        )
    )
    progress = result.scalar_one()
    assert progress.quiz_attempts_count == 1
    assert progress.is_completed is False  # Not completed since failed


@pytest.mark.asyncio
async def test_invalid_language_selection(test_db):
    """Test handling of invalid language selection"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    # Setup user
    user = User(
        phone_number="+2348012345683",
        name="Test User 6",
        language=Language.ENGLISH,
        current_day=1,
        consent_given=True,
        data_retention_date=datetime.utcnow() + timedelta(days=90)
    )
    test_db.add(user)
    await test_db.flush()

    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number="+2348012345683",
        current_state=ConversationState.AWAITING_LANGUAGE,
        is_active=True
    )
    test_db.add(conversation)
    await test_db.commit()

    # Try invalid language
    await handler.handle_language_selection(user, conversation, "invalid_lang")

    # Should still be in AWAITING_LANGUAGE state
    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.AWAITING_LANGUAGE

    # Language should not have changed
    await test_db.refresh(user)
    assert user.language == Language.ENGLISH  # Still default
