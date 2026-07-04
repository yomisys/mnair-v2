"""
Tests for the free WhatsApp window reminder feature:
- last_active_at tracking on inbound messages
- localized reminder message builder
- CONTINUE resume handler
- hourly nudge task eligibility window + Redis dedupe
"""

import pytest
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.user import User, Language, UserRole
from app.models.lesson import Lesson
from app.models.conversation import Conversation, ConversationState
from app.channels.whatsapp import WhatsAppWebhookHandler, WhatsAppMessageBuilder
from app.config import Settings
from app.tasks import notification_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SessionCtx:
    """Async context manager wrapping the test session, mimics AsyncSessionLocal()"""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


class FakeRedis:
    """Minimal async Redis stub supporting SET NX EX and DELETE"""

    def __init__(self):
        self.store = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)

    async def close(self):
        pass


def make_learner(phone, *, channel="whatsapp", hours_inactive=None,
                 completed_days=0, current_day=1, consent=True, active=True,
                 language=Language.ENGLISH):
    user = User(
        phone_number=phone,
        name=f"Learner {phone[-4:]}",
        language=language,
        role=UserRole.LEARNER,
        current_day=current_day,
        completed_days=completed_days,
        preferred_channel=channel,
        consent_given=consent,
        is_active=active,
    )
    if hours_inactive is not None:
        user.last_active_at = datetime.utcnow() - timedelta(hours=hours_inactive)
    return user


@pytest.fixture
def capture_sends(monkeypatch):
    """Capture outbound WhatsApp messages instead of hitting Meta's API"""
    sent = []

    async def fake_send(self, phone_number, message):
        sent.append((phone_number, message))
        return True

    monkeypatch.setattr(WhatsAppWebhookHandler, "send_whatsapp_message", fake_send)
    return sent


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(
        notification_tasks.redis_asyncio, "from_url", lambda url: fake
    )
    return fake


@pytest.fixture
def task_session(monkeypatch, test_db):
    """Point the Celery task helpers at the test database session"""
    monkeypatch.setattr(
        notification_tasks, "AsyncSessionLocal", lambda: _SessionCtx(test_db)
    )
    return test_db


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_reminder_message_all_languages(test_db):
    """Reminder builds for all 5 languages with a valid Continue button"""
    for language in Language:
        msg = WhatsAppMessageBuilder.build_reminder_message(language, 3, 5)

        assert msg["messaging_product"] == "whatsapp"
        assert msg["type"] == "interactive"
        assert msg["interactive"]["type"] == "button"

        body = msg["interactive"]["body"]["text"]
        assert "3" in body, f"day number missing for {language}"
        assert "5" in body, f"days_left missing for {language}"

        buttons = msg["interactive"]["action"]["buttons"]
        assert len(buttons) == 1
        assert buttons[0]["reply"]["id"] == "continue_learning"
        # WhatsApp caps button titles at 20 characters
        assert len(buttons[0]["reply"]["title"]) <= 20


@pytest.mark.asyncio
async def test_build_reminder_message_singular_plural(test_db):
    """English copy handles 1 day vs N days"""
    singular = WhatsAppMessageBuilder.build_reminder_message(Language.ENGLISH, 7, 1)
    assert "1 day left" in singular["interactive"]["body"]["text"]

    plural = WhatsAppMessageBuilder.build_reminder_message(Language.ENGLISH, 2, 6)
    assert "6 days left" in plural["interactive"]["body"]["text"]


@pytest.mark.asyncio
async def test_build_reminder_message_unknown_language_falls_back(test_db):
    """Unexpected language value falls back to English instead of crashing"""
    msg = WhatsAppMessageBuilder.build_reminder_message("not-a-language", 2, 5)
    assert "Tap Continue" in msg["interactive"]["body"]["text"]


# ---------------------------------------------------------------------------
# last_active_at tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_message_sets_last_active_at(test_db, capture_sends):
    """Every inbound WhatsApp message stamps the user's last_active_at"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    before = datetime.utcnow() - timedelta(seconds=5)
    await handler.handle_message("+2348012345678", "hello", "text")

    result = await test_db.execute(
        select(User).where(User.phone_number == "+2348012345678")
    )
    user = result.scalar_one()
    assert user.last_active_at is not None
    assert user.last_active_at >= before


# ---------------------------------------------------------------------------
# CONTINUE resume handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_continue_button_resends_current_lesson(test_db, capture_sends):
    """Tapping Continue while IN_LESSON re-delivers the pending lesson"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    lesson = Lesson(
        lesson_id="d1_what_is_ai_en",
        day=1,
        topic="what_is_ai",
        language="en",
        title="What is AI?",
        content="AI helps computers learn.",
        word_count=4,
        quiz=[{"question": "Q", "options": ["A", "B", "C", "D"], "correct": 0}] * 5,
    )
    test_db.add(lesson)

    user = make_learner("+2348011110001", hours_inactive=21)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number=user.phone_number,
        current_state=ConversationState.IN_LESSON,
        is_active=True,
        context={"current_lesson_id": lesson.id},
    )
    test_db.add(conversation)
    await test_db.commit()

    await handler.handle_message(
        user.phone_number, "", "interactive", interactive_id="continue_learning"
    )

    assert len(capture_sends) == 1
    body = capture_sends[0][1]["text"]["body"]
    assert "What is AI?" in body


@pytest.mark.asyncio
async def test_typed_continue_resends_quiz_question(test_db, capture_sends):
    """Typing CONTINUE while AWAITING_QUIZ re-sends the current question"""
    settings = Settings()
    handler = WhatsAppWebhookHandler(settings, test_db)

    lesson = Lesson(
        lesson_id="d1_how_ai_works_en",
        day=1,
        topic="how_ai_works",
        language="en",
        title="How AI Works",
        content="Content",
        word_count=1,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": 0} for i in range(5)],
    )
    test_db.add(lesson)

    user = make_learner("+2348011110002")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    conversation = Conversation(
        user_id=user.id,
        channel="whatsapp",
        phone_number=user.phone_number,
        current_state=ConversationState.AWAITING_QUIZ,
        is_active=True,
        context={"current_lesson_id": lesson.id, "current_question": 2, "answers": [0, 1]},
    )
    test_db.add(conversation)
    await test_db.commit()

    await handler.handle_message(user.phone_number, "continue", "text")

    assert len(capture_sends) == 1
    quiz_body = capture_sends[0][1]["interactive"]["body"]["text"]
    assert "Question 3/5" in quiz_body
    assert "Q2" in quiz_body


# ---------------------------------------------------------------------------
# Window reminder task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_window_reminder_eligibility(task_session, fake_redis, capture_sends):
    """Only mid-course WhatsApp learners inactive 20-23h get nudged"""
    users = [
        make_learner("+2348020000001", hours_inactive=21),                      # eligible
        make_learner("+2348020000002", hours_inactive=5),                       # too recent
        make_learner("+2348020000003", hours_inactive=30),                      # window closed
        make_learner("+2348020000004", hours_inactive=21, channel="ussd"),      # wrong channel
        make_learner("+2348020000005", hours_inactive=21, completed_days=7),    # finished course
        make_learner("+2348020000006", hours_inactive=21, consent=False),       # no consent
        make_learner("+2348020000007", hours_inactive=21, active=False),        # deactivated
    ]
    task_session.add_all(users)
    await task_session.commit()

    result = await notification_tasks._send_whatsapp_window_reminders_async()

    assert result["total_eligible"] == 1
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert len(capture_sends) == 1
    assert capture_sends[0][0] == "+2348020000001"


@pytest.mark.asyncio
async def test_window_reminder_dedupes_per_episode(task_session, fake_redis, capture_sends):
    """A second run within the same inactivity episode sends nothing"""
    user = make_learner("+2348020000010", hours_inactive=21, completed_days=3, current_day=4)
    task_session.add(user)
    await task_session.commit()

    first = await notification_tasks._send_whatsapp_window_reminders_async()
    second = await notification_tasks._send_whatsapp_window_reminders_async()

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped"] == 1
    assert len(capture_sends) == 1

    # Certificate countdown reflects progress: 7 - 3 completed = 4 days left
    body = capture_sends[0][1]["interactive"]["body"]["text"]
    assert "4 days left" in body


@pytest.mark.asyncio
async def test_window_reminder_releases_dedupe_on_send_failure(
    task_session, fake_redis, monkeypatch
):
    """Failed sends release the dedupe key so the next hourly run can retry"""

    async def failing_send(self, phone_number, message):
        return False

    monkeypatch.setattr(WhatsAppWebhookHandler, "send_whatsapp_message", failing_send)

    user = make_learner("+2348020000020", hours_inactive=21)
    task_session.add(user)
    await task_session.commit()

    result = await notification_tasks._send_whatsapp_window_reminders_async()

    assert result["failed"] == 1
    assert result["sent"] == 0
    assert fake_redis.store == {}


# ---------------------------------------------------------------------------
# Existing SMS reminder task — timezone regression
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sms_reminder_task_handles_naive_and_aware_datetimes(task_session, monkeypatch):
    """The 3/7/14-day SMS reminder must not crash on datetime arithmetic
    (learners now populate last_active_at, activating this dormant path)"""
    from app.channels.sms import SMSNotifier

    sms_calls = []

    async def fake_reminder_sms(self, user, days_inactive):
        sms_calls.append((user.phone_number, days_inactive))
        return True

    monkeypatch.setattr(SMSNotifier, "send_reminder_sms", fake_reminder_sms)

    user = make_learner("+2348030000001", channel="sms")
    user.last_active_at = datetime.utcnow() - timedelta(days=3, minutes=5)
    task_session.add(user)
    await task_session.commit()

    result = await notification_tasks._send_reminders_async()

    assert result["status"] == "success"
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert sms_calls == [("+2348030000001", 3)]
