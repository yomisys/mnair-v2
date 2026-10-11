"""
Outbound routing tests: NotificationRouter prefers free channels, SMS is
opt-in, and the Celery reminder/certificate tasks use the router.
"""

import pytest
from datetime import datetime, timedelta

from sqlalchemy import select

from app.channels.notify import NotificationRouter
from app.config import Settings
from app.models.push_subscription import PushSubscription
from app.models.reminder_log import ReminderLog
from app.models.user import User, Language, UserRole
from app.tasks import notification_tasks


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


class FakeRedis:
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


class FakeTelegram:
    def __init__(self, ok=True):
        self.sent = []
        self.ok = ok

    async def send_message(self, chat_id, message):
        self.sent.append((chat_id, message))
        return self.ok


class FakeWebPush:
    def __init__(self, db, ok=True):
        self.db = db
        self.sent = []
        self.ok = ok

    async def subscriptions_for(self, user):
        return (await self.db.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))).scalars().all()

    async def send_to_user(self, user, title, body, url=None):
        self.sent.append((user.id, title, body, url))
        return self.ok


class FakeSMS:
    def __init__(self):
        self.sent = []

    async def send_reminder_sms(self, user, days_inactive):
        self.sent.append(("reminder", user.id))
        return True

    async def send_certificate_ready_sms(self, user, code):
        self.sent.append(("cert", user.id, code))
        return True


def make_learner(identity, *, channel, hours_inactive=None, telegram_chat_id=None,
                 completed_days=0, current_day=1, language=Language.ENGLISH):
    user = User(
        phone_number=identity,
        name="Learner",
        language=language,
        role=UserRole.LEARNER,
        current_day=current_day,
        completed_days=completed_days,
        preferred_channel=channel,
        telegram_chat_id=telegram_chat_id,
        consent_given=True,
        is_active=True,
    )
    if hours_inactive is not None:
        user.last_active_at = datetime.utcnow() - timedelta(hours=hours_inactive)
    return user


def build_router(db, settings=None, **fakes):
    settings = settings or Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t")
    return NotificationRouter(
        db, settings,
        telegram=fakes.get("telegram", FakeTelegram()),
        webpush=fakes.get("webpush", FakeWebPush(db)),
        sms=fakes.get("sms", FakeSMS()),
    )


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(notification_tasks.redis_asyncio, "from_url", lambda url: fake)
    return fake


@pytest.fixture
def task_session(monkeypatch, test_db):
    monkeypatch.setattr(notification_tasks, "AsyncSessionLocal", lambda: _SessionCtx(test_db))
    return test_db


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_prefers_telegram(test_db):
    user = make_learner("tg:5", channel="telegram", telegram_chat_id="5", current_day=3, language=Language.HAUSA)
    test_db.add(user)
    await test_db.commit()

    telegram = FakeTelegram()
    router = build_router(test_db, telegram=telegram)
    channel, ok = await router.send_reminder(user, days_left=4)
    assert (channel, ok) == ("telegram", True)
    chat_id, message = telegram.sent[0]
    assert chat_id == 5
    assert "Rana ta 3" in message.text  # Hausa copy
    assert [b.id for b in message.buttons] == ["continue_learning"]


@pytest.mark.asyncio
async def test_router_uses_webpush_for_web_learners(test_db):
    user = make_learner("+2348031111111", channel="web", current_day=2)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    test_db.add(PushSubscription(user_id=user.id, endpoint="https://p/1", p256dh="k", auth="a"))
    await test_db.commit()

    webpush = FakeWebPush(test_db)
    router = build_router(test_db, webpush=webpush)
    channel, ok = await router.send_reminder(user, days_left=5)
    assert (channel, ok) == ("webpush", True)
    assert webpush.sent[0][3].endswith("/learn")

    channel, ok = await router.send_certificate_ready(user, "MNAIR-2026-9-XYZ")
    assert channel == "webpush"
    assert "MNAIR-2026-9-XYZ" in webpush.sent[1][2]
    assert "/verify?code=MNAIR-2026-9-XYZ" in webpush.sent[1][3]


@pytest.mark.asyncio
async def test_router_never_sends_sms_unless_enabled(test_db):
    user = make_learner("+2348032222222", channel="ussd", current_day=2)
    test_db.add(user)
    await test_db.commit()

    sms = FakeSMS()
    router = build_router(test_db, sms=sms)
    assert await router.send_reminder(user, days_left=5) == ("none", False)
    assert await router.send_certificate_ready(user, "C") == ("none", False)
    assert sms.sent == []

    enabled = Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t", SMS_REMINDERS_ENABLED=True)
    router = build_router(test_db, settings=enabled, sms=sms)
    assert await router.send_reminder(user, days_left=5) == ("sms", True)
    assert sms.sent == [("reminder", user.id)]


@pytest.mark.asyncio
async def test_router_sms_fallback_skips_non_phone_identities(test_db):
    """A Telegram learner without a chat id (shouldn't happen) must not
    trigger an SMS to 'tg:123'."""
    user = make_learner("tg:123", channel="telegram")
    test_db.add(user)
    await test_db.commit()
    sms = FakeSMS()
    enabled = Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t", SMS_REMINDERS_ENABLED=True)
    router = build_router(test_db, settings=enabled, sms=sms)
    assert await router.send_reminder(user, days_left=1) == ("none", False)
    assert sms.sent == []


# ---------------------------------------------------------------------------
# hourly nudge task
# ---------------------------------------------------------------------------

@pytest.fixture
def capture_router(monkeypatch, test_db):
    """Swap the router the tasks build for one with fake senders."""
    telegram, webpush, sms = FakeTelegram(), FakeWebPush(test_db), FakeSMS()

    def factory(db, settings):
        return NotificationRouter(db, settings, telegram=telegram, webpush=webpush, sms=sms)

    monkeypatch.setattr(notification_tasks, "NotificationRouter", factory)
    return telegram, webpush, sms


@pytest.mark.asyncio
async def test_daily_nudge_eligibility_window(task_session, fake_redis, capture_router):
    telegram, webpush, sms = capture_router
    task_session.add_all([
        make_learner("tg:1", channel="telegram", telegram_chat_id="1", hours_inactive=21),   # eligible
        make_learner("tg:2", channel="telegram", telegram_chat_id="2", hours_inactive=5),    # too recent
        make_learner("tg:3", channel="telegram", telegram_chat_id="3", hours_inactive=30),   # too old
        make_learner("tg:4", channel="telegram", telegram_chat_id="4", hours_inactive=21, completed_days=7),  # done
        make_learner("+2348030000005", channel="ussd", hours_inactive=21),                  # not a free channel
    ])
    await task_session.commit()

    result = await notification_tasks._send_daily_nudges_async()
    assert result["total_eligible"] == 1
    assert result["sent"] == 1
    assert [c for c, _ in telegram.sent] == [1]
    assert sms.sent == []

    logs = (await task_session.execute(select(ReminderLog))).scalars().all()
    assert len(logs) == 1 and logs[0].channel == "telegram" and logs[0].status == "sent"


@pytest.mark.asyncio
async def test_daily_nudge_dedupes_per_episode(task_session, fake_redis, capture_router):
    telegram, _, _ = capture_router
    task_session.add(make_learner("tg:1", channel="telegram", telegram_chat_id="1", hours_inactive=21))
    await task_session.commit()

    first = await notification_tasks._send_daily_nudges_async()
    second = await notification_tasks._send_daily_nudges_async()
    assert first["sent"] == 1 and second["sent"] == 0 and second["skipped"] == 1
    assert len(telegram.sent) == 1


@pytest.mark.asyncio
async def test_daily_nudge_web_learner_without_push_is_unreachable_not_sms(task_session, fake_redis, capture_router):
    telegram, webpush, sms = capture_router
    task_session.add(make_learner("+2348030000009", channel="web", hours_inactive=21))
    await task_session.commit()

    result = await notification_tasks._send_daily_nudges_async()
    assert result["unreachable"] == 1 and result["sent"] == 0
    assert sms.sent == [] and webpush.sent == []
    # key released so a later subscription can still be nudged in this episode
    assert fake_redis.store == {}


@pytest.mark.asyncio
async def test_daily_nudge_releases_dedupe_on_failure(task_session, fake_redis, capture_router, monkeypatch):
    telegram, _, _ = capture_router
    telegram.ok = False
    task_session.add(make_learner("tg:1", channel="telegram", telegram_chat_id="1", hours_inactive=21))
    await task_session.commit()

    result = await notification_tasks._send_daily_nudges_async()
    assert result["failed"] == 1
    assert fake_redis.store == {}
    logs = (await task_session.execute(select(ReminderLog))).scalars().all()
    assert logs[0].status == "failed"


# ---------------------------------------------------------------------------
# 3/7/14-day task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inactive_reminders_route_free_first(task_session, capture_router):
    telegram, webpush, sms = capture_router
    tg_user = make_learner("tg:7", channel="telegram", telegram_chat_id="7", hours_inactive=24 * 3 + 1, current_day=2)
    web_user = make_learner("+2348030000010", channel="web", hours_inactive=24 * 7 + 1, current_day=4)
    ussd_user = make_learner("+2348030000011", channel="ussd", hours_inactive=24 * 3 + 1, current_day=2)
    off_cycle = make_learner("tg:8", channel="telegram", telegram_chat_id="8", hours_inactive=24 * 5, current_day=2)
    task_session.add_all([tg_user, web_user, ussd_user, off_cycle])
    await task_session.commit()
    await task_session.refresh(web_user)
    task_session.add(PushSubscription(user_id=web_user.id, endpoint="https://p/2", p256dh="k", auth="a"))
    await task_session.commit()

    result = await notification_tasks._send_reminders_async()
    assert result["sent"] == 2
    assert result["skipped"] == 1       # off-cycle (5 days)
    assert result["unreachable"] == 1   # USSD learner, SMS disabled
    assert [c for c, _ in telegram.sent] == [7]
    assert len(webpush.sent) == 1
    assert sms.sent == []

    channels = sorted(l.channel for l in (await task_session.execute(select(ReminderLog))).scalars().all())
    assert channels == ["telegram", "webpush"]


# ---------------------------------------------------------------------------
# certificates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_certificate_task_notifies_via_free_channel(task_session, capture_router, monkeypatch):
    telegram, _, _ = capture_router
    user = make_learner("tg:70", channel="telegram", telegram_chat_id="70", current_day=7, completed_days=7)
    user.name = "Bola Ahmed"
    user.name_confirmed = True
    unnamed = make_learner("tg:71", channel="telegram", telegram_chat_id="71", current_day=7, completed_days=7)
    task_session.add_all([user, unnamed])
    await task_session.commit()

    class FakeCert:
        certificate_id = "MNAIR-2026-70-ZZZZ"
        is_verified = True

    from app.certificates.generator import CertificateGenerator

    async def none(self, user_id):
        return None

    async def gen(self, user_id, language):
        return FakeCert()

    monkeypatch.setattr(CertificateGenerator, "__init__", lambda self, db, settings: None)
    monkeypatch.setattr(CertificateGenerator, "get_user_certificate", none)
    monkeypatch.setattr(CertificateGenerator, "generate_and_store_certificate", gen)

    result = await notification_tasks._generate_certificates_async()
    assert result["generated"] == 1          # unnamed learner is skipped by the query
    assert result["notify_failed"] == 0
    chat_id, message = telegram.sent[0]
    assert chat_id == 70 and message.kind == "certificate"
    assert "Bola Ahmed" in message.text and "MNAIR-2026-70-ZZZZ" in message.text
