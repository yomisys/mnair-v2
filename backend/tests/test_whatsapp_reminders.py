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


# ---------------------------------------------------------------------------
# Reminder logging + analytics endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_window_reminder_writes_reminder_log(task_session, fake_redis, capture_sends):
    """Every nudge attempt is recorded for the dashboard"""
    from app.models.reminder_log import ReminderLog

    user = make_learner("+2348040000001", hours_inactive=21, current_day=3)
    task_session.add(user)
    await task_session.commit()

    await notification_tasks._send_whatsapp_window_reminders_async()

    logs = (await task_session.execute(select(ReminderLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].channel == "whatsapp"
    assert logs[0].status == "sent"
    assert logs[0].current_day == 3
    assert logs[0].sent_at is not None


@pytest.mark.asyncio
async def test_window_reminder_logs_failures(task_session, fake_redis, monkeypatch):
    """Failed sends are recorded too, so the dashboard shows delivery problems"""
    from app.models.reminder_log import ReminderLog

    async def failing_send(self, phone_number, message):
        return False

    monkeypatch.setattr(WhatsAppWebhookHandler, "send_whatsapp_message", failing_send)

    user = make_learner("+2348040000002", hours_inactive=21)
    task_session.add(user)
    await task_session.commit()

    await notification_tasks._send_whatsapp_window_reminders_async()

    logs = (await task_session.execute(select(ReminderLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "failed"


@pytest.mark.asyncio
async def test_reminder_analytics_endpoint(test_db):
    """Aggregation: totals, channel breakdown, daily series, re-engagement rate"""
    from app.models.reminder_log import ReminderLog
    from app.routers.analytics import get_reminder_analytics

    # Two nudged users: one came back after the nudge, one never returned
    returned = make_learner("+2348050000001")
    ghosted = make_learner("+2348050000002")
    test_db.add_all([returned, ghosted])
    await test_db.commit()
    await test_db.refresh(returned)
    await test_db.refresh(ghosted)

    nudge_time = datetime.utcnow() - timedelta(hours=10)
    returned.last_active_at = datetime.utcnow() - timedelta(hours=2)   # after nudge
    ghosted.last_active_at = datetime.utcnow() - timedelta(hours=31)   # before nudge

    test_db.add_all([
        ReminderLog(user_id=returned.id, channel="whatsapp", status="sent",
                    current_day=2, sent_at=nudge_time),
        ReminderLog(user_id=ghosted.id, channel="whatsapp", status="sent",
                    current_day=4, sent_at=nudge_time),
        ReminderLog(user_id=ghosted.id, channel="sms", status="failed",
                    current_day=4, sent_at=nudge_time),
    ])
    await test_db.commit()

    stats = await get_reminder_analytics(days=30, current_user=None, db=test_db)

    assert stats.total_sent == 2
    assert stats.total_failed == 1
    assert stats.total_re_engaged == 1
    assert stats.re_engagement_rate == 50.0

    channels = {c.channel: c for c in stats.by_channel}
    assert channels["whatsapp"].sent == 2
    assert channels["whatsapp"].re_engaged == 1
    assert channels["whatsapp"].re_engagement_rate == 50.0
    assert channels["sms"].failed == 1
    assert channels["sms"].re_engagement_rate == 0

    assert len(stats.daily) == 1
    assert stats.daily[0].sent == 2
    assert stats.daily[0].failed == 1
    assert stats.daily[0].re_engaged == 1


@pytest.mark.asyncio
async def test_reminder_analytics_endpoint_empty(test_db):
    """No reminders yet — endpoint returns zeros, not errors"""
    from app.routers.analytics import get_reminder_analytics

    stats = await get_reminder_analytics(days=30, current_user=None, db=test_db)

    assert stats.total_sent == 0
    assert stats.re_engagement_rate == 0
    assert stats.by_channel == []
    assert stats.daily == []


# ---------------------------------------------------------------------------
# Certificate delivery — regression coverage for the "no certificate after
# completing Day 7" bug. The nightly auto_generate_certificates task
# generates the cert correctly (gated on current_day, which does reach 7);
# the actual failure was in notifying the learner it exists.
# ---------------------------------------------------------------------------

@pytest.fixture
def capture_sms(monkeypatch):
    """Capture certificate-ready SMS sends instead of hitting Termii"""
    from app.channels.sms import SMSNotifier
    sent = []

    async def fake_send_certificate_sms(self, user, certificate_code):
        sent.append((user.phone_number, certificate_code))
        return True

    monkeypatch.setattr(SMSNotifier, "send_certificate_ready_sms", fake_send_certificate_sms)
    return sent


@pytest.fixture(autouse=True)
def mock_minio_for_certificate_tests(monkeypatch):
    """
    Certificate generation touches MinIO for bucket setup + PDF upload.
    These tests exercise the notification logic around generation, not
    storage, so MinIO is stubbed the same way test_sms_and_certificates.py
    stubs it for unit tests — avoids a real network call to a service that
    may not be reachable from wherever pytest happens to run.
    """
    from app.certificates.generator import CertificateGenerator

    monkeypatch.setattr(CertificateGenerator, "_ensure_bucket_exists", lambda self: None)

    async def fake_upload(self, pdf_bytes, certificate_code):
        return f"certificates/{certificate_code}.pdf"

    monkeypatch.setattr(CertificateGenerator, "upload_to_minio", fake_upload)


def make_finisher(phone, *, channel="whatsapp", language=Language.ENGLISH):
    return User(
        phone_number=phone,
        name=f"Finisher {phone[-4:]}",
        language=language,
        role=UserRole.LEARNER,
        current_day=7,
        completed_days=7,
        preferred_channel=channel,
        consent_given=True,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_certificate_task_notifies_whatsapp_users_via_whatsapp(
    task_session, capture_sends, capture_sms
):
    """WhatsApp learners get a WhatsApp certificate-ready message, not just
    an SMS they may never see (SMS is unreliable — see Termii auth findings)."""
    user = make_finisher("+2348060000001", channel="whatsapp")
    task_session.add(user)
    await task_session.commit()

    result = await notification_tasks._generate_certificates_async()

    assert result["generated"] == 1
    assert result["notify_failed"] == 0
    assert len(capture_sends) == 1  # WhatsApp message sent
    assert len(capture_sms) == 1    # SMS also attempted as a second channel

    body = capture_sends[0][1]["text"]["body"]
    assert "certificate is ready" in body.lower()
    assert "mnair.ng" in body
    assert "mnair.gov.ng" not in body


@pytest.mark.asyncio
async def test_certificate_task_sms_only_user_no_whatsapp_attempt(
    task_session, capture_sends, capture_sms
):
    """USSD/SMS-only learners aren't sent a WhatsApp message (they never
    messaged the WhatsApp number, so a free-form send would fail anyway)."""
    user = make_finisher("+2348060000002", channel="ussd")
    task_session.add(user)
    await task_session.commit()

    result = await notification_tasks._generate_certificates_async()

    assert result["generated"] == 1
    assert len(capture_sends) == 0  # no WhatsApp attempt for a USSD user
    assert len(capture_sms) == 1


@pytest.mark.asyncio
async def test_certificate_task_flags_total_notification_failure(
    task_session, monkeypatch
):
    """
    When every notification channel fails, the task must say so distinctly
    from a plain generation failure — this is exactly the silent-failure gap
    that made a completed certificate invisible to the learner and to
    operators reading the logs (the old code logged "Generated certificate
    X" regardless of whether the SMS send actually succeeded).
    """
    from app.channels.sms import SMSNotifier

    async def failing_sms(self, user, certificate_code):
        return False

    async def failing_whatsapp(self, phone_number, message):
        return False

    monkeypatch.setattr(SMSNotifier, "send_certificate_ready_sms", failing_sms)
    monkeypatch.setattr(WhatsAppWebhookHandler, "send_whatsapp_message", failing_whatsapp)

    user = make_finisher("+2348060000003", channel="whatsapp")
    task_session.add(user)
    await task_session.commit()

    result = await notification_tasks._generate_certificates_async()

    # The certificate itself was still created — this is a notify failure,
    # not a generation failure
    assert result["generated"] == 1
    assert result["failed"] == 0
    assert result["notify_failed"] == 1
