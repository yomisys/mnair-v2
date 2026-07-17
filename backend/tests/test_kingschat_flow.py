"""
Tests for the KingsChat channel adapter.

Covers the 3 critical gaps flagged in /plan-eng-review's failure-modes
table (2026-07-12) — each of these was "no test + no error handling +
silent to the user" before this file existed:

1. Session-store file missing/corrupted — must fail loudly, not silently
   (test_session_store_*).
2. Quiz-shuffle context-threading regression — same bug class fixed in
   whatsapp.py earlier that session, re-tested here for kingschat.py
   (test_quiz_shuffle_context_not_discarded).
3. Login-session expiry / ban detection — send_message now navigates and
   sends against real, verified selectors (see kingschat.py's module
   docstring for what was confirmed live on 2026-07-12); tested here with
   a mocked Playwright page. detect_ban's two selectors remain unverified
   against a real ban event and are tested as "best effort, not gospel."

Also covers the config validator (required-env-vars-when-enabled, per
Architecture Issue 1) and the BrowserContext pool (per Architecture
Issue 2 and the Performance Review's pool-sizing decision).
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.kingschat import (
    KINGSCHAT_ID_PREFIX,
    DryRunKingsChatSession,
    KingsChatBanDetectedError,
    KingsChatBanFallback,
    KingsChatHandler,
    KingsChatLoginError,
    KingsChatMessageBuilder,
    KingsChatSession,
    KingsChatWatcher,
    SELECTORS,
    SelectorDriftError,
    kingschat_login,
)
from app.config import Settings
from app.models.conversation import Conversation, ConversationChannel, ConversationState
from app.models.lesson import Lesson
from app.services.kingschat_browser_pool import KingsChatBrowserPool, PoolExhaustedTimeout
from app.services.kingschat_session_store import KingsChatSessionStore, SessionStoreError


def _quiz_lesson(correct_at_zero: bool = True) -> Lesson:
    correct = 0 if correct_at_zero else 2
    return Lesson(
        lesson_id="test_lesson",
        day=1,
        topic="what_is_ai",
        language="en",
        title="What is AI?",
        content="AI is a technology that helps computers learn.",
        word_count=10,
        quiz=[{"question": f"Q{i}", "options": ["A", "B", "C", "D"], "correct": correct} for i in range(5)],
    )


# ---------------------------------------------------------------------------
# Critical gap 1: session store missing/corrupted file must fail loudly
# ---------------------------------------------------------------------------

def test_session_store_missing_file_returns_none_not_a_crash(tmp_path):
    """First-run case: no session saved yet. Must return None so the caller
    falls through to an interactive login, not raise."""
    store = KingsChatSessionStore(
        path=str(tmp_path / "does_not_exist.kingschat-session"),
        encryption_key=_fernet_key(),
    )
    assert store.load() is None


def test_session_store_empty_file_raises_loudly(tmp_path):
    """An empty file means a write was interrupted mid-flight — this is a
    real failure state and must surface, not be silently treated as
    'no session' (which would mask data loss)."""
    path = tmp_path / "corrupted.kingschat-session"
    path.write_bytes(b"")
    store = KingsChatSessionStore(path=str(path), encryption_key=_fernet_key())

    with pytest.raises(SessionStoreError):
        store.load()


def test_session_store_wrong_key_raises_loudly(tmp_path):
    from cryptography.fernet import Fernet

    path = tmp_path / "session.kingschat-session"
    write_key = Fernet.generate_key().decode()
    KingsChatSessionStore(path=str(path), encryption_key=write_key).save({"cookies": []})

    read_store = KingsChatSessionStore(path=str(path), encryption_key=_fernet_key())
    with pytest.raises(SessionStoreError):
        read_store.load()


def test_session_store_round_trip(tmp_path):
    key = _fernet_key()
    path = tmp_path / "session.kingschat-session"
    store = KingsChatSessionStore(path=str(path), encryption_key=key)

    storage_state = {"cookies": [{"name": "sid", "value": "abc123"}]}
    store.save(storage_state)

    # File must actually be encrypted at rest -- not plaintext JSON on disk.
    raw = path.read_bytes()
    assert b"sid" not in raw
    assert b"abc123" not in raw

    loaded = KingsChatSessionStore(path=str(path), encryption_key=key).load()
    assert loaded == storage_state


def test_session_store_invalid_key_raises_on_construction():
    with pytest.raises(SessionStoreError):
        KingsChatSessionStore(path="/tmp/whatever", encryption_key="not-a-valid-fernet-key")


def _fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# Critical gap 2: quiz-shuffle context threading (same bug class as
# whatsapp.py's fixed context-discard bug)
# ---------------------------------------------------------------------------

class _FakeSession:
    """Stands in for KingsChatSession — records sent messages instead of
    driving a real (unimplemented) Playwright page."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, kingschat_user_id: str, text: str) -> None:
        self.sent.append((kingschat_user_id, text))


@pytest.mark.asyncio
async def test_quiz_shuffle_context_not_discarded(test_db):
    """Mirrors backend/tests/test_whatsapp_flow.py's regression test for the
    context-discard bug: a freshly-created shuffle for the CURRENT question
    (created defensively inside handle_quiz_response, not pre-seeded by
    handle_lesson_flow) must not be lost when the NEXT question's shuffle is
    folded into the context afterward.
    """
    lesson = _quiz_lesson(correct_at_zero=True)
    test_db.add(lesson)
    await test_db.commit()
    await test_db.refresh(lesson)

    handler = KingsChatHandler(settings=None, db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user123")
    conversation = await handler.get_or_create_conversation(user.id, "user123")

    # Simulate arriving at AWAITING_QUIZ with NO shuffle already in context
    # (the defensive-fallback scenario) rather than going through
    # handle_lesson_flow, to isolate the exact bug class.
    conversation.current_state = ConversationState.AWAITING_QUIZ
    conversation.context = {"current_lesson_id": lesson.id, "current_question": 0, "answers": []}
    await test_db.commit()

    # correct=0 for every question -> option A is always correct pre-shuffle.
    # Reply "A" and let the handler create + apply this question's shuffle
    # on the fly.
    await handler.handle_quiz_response(session, "user123", user, conversation, "A")

    # If the freshly-created shuffle for question 0 was discarded (the
    # exact bug this test guards against), conversation.context would only
    # contain question 1's shuffle, and re-deriving question 0's answer on
    # a later resend would silently regenerate a NEW random order --
    # breaking the "same order the learner already saw" contract.
    assert "0" in conversation.context.get("quiz_shuffle", {}), (
        "question 0's shuffle was discarded when question 1's shuffle was "
        "folded into context -- this is the exact context-discard bug "
        "fixed in whatsapp.py, recurring in kingschat.py"
    )
    assert conversation.context["current_question"] == 1
    assert len(session.sent) == 1
    assert "Question 2/5" in session.sent[0][1]


@pytest.mark.asyncio
async def test_quiz_full_flow_grades_against_original_index_not_display_position(test_db):
    """The correct answer is stored at index 0, but shuffling means it
    won't always display at letter A -- answering by the DISPLAYED letter
    must still grade against the original index."""
    lesson = _quiz_lesson(correct_at_zero=True)
    test_db.add(lesson)
    await test_db.commit()
    await test_db.refresh(lesson)

    handler = KingsChatHandler(settings=None, db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user456")
    conversation = await handler.get_or_create_conversation(user.id, "user456")
    conversation.current_state = ConversationState.IN_LESSON
    conversation.context = {"current_lesson_id": lesson.id}
    await test_db.commit()

    await handler.handle_lesson_flow(session, "user456", user, conversation, "QUIZ")
    assert conversation.current_state == ConversationState.AWAITING_QUIZ

    # Read back the actual shuffle order for question 0 and answer with
    # whatever letter the correct option (original index 0) landed at --
    # not always "A".
    order = conversation.context["quiz_shuffle"]["0"]
    correct_letter = chr(65 + order.index(0))

    for q in range(5):
        order = conversation.context["quiz_shuffle"][str(q)]
        letter = chr(65 + order.index(0))
        await handler.handle_quiz_response(session, "user456", user, conversation, letter)

    result_text = session.sent[-1][1]
    assert "Congratulations" in result_text or "🎉" in result_text


# ---------------------------------------------------------------------------
# Stranded-learner recovery (regression for a failure reproduced live
# 2026-07-17): handle_language_selection commits IN_LESSON before
# deliver_next_lesson's send confirms, so a transient send failure leaves
# the conversation in IN_LESSON with an empty context and the learner with
# no lesson. Any subsequent reply must re-deliver the lesson — not send a
# "Reply QUIZ" reminder about a lesson that never arrived.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stranded_in_lesson_with_no_lesson_redelivers_on_any_reply(test_db):
    lesson = _quiz_lesson()
    test_db.add(lesson)
    await test_db.commit()
    await test_db.refresh(lesson)

    handler = KingsChatHandler(settings=None, db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user_stranded")
    conversation = await handler.get_or_create_conversation(user.id, "user_stranded")
    # The exact stranded state observed live: IN_LESSON committed, send
    # failed before context could record which lesson went out.
    conversation.current_state = ConversationState.IN_LESSON
    conversation.context = {}
    await test_db.commit()

    # A non-QUIZ reply ("hello") must re-deliver the lesson, not remind
    # about a quiz for a lesson the learner never received.
    await handler.handle_lesson_flow(session, "user_stranded", user, conversation, "hello")

    assert len(session.sent) == 1
    assert lesson.title in session.sent[0][1]
    assert conversation.context.get("current_lesson_id") == lesson.id


@pytest.mark.asyncio
async def test_in_lesson_with_lesson_on_record_still_gets_quiz_reminder(test_db):
    """The recovery path must not swallow the normal reminder: when a
    lesson IS on record, an off-script reply still gets the QUIZ nudge."""
    lesson = _quiz_lesson()
    test_db.add(lesson)
    await test_db.commit()
    await test_db.refresh(lesson)

    handler = KingsChatHandler(settings=None, db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user_reminder")
    conversation = await handler.get_or_create_conversation(user.id, "user_reminder")
    conversation.current_state = ConversationState.IN_LESSON
    conversation.context = {"current_lesson_id": lesson.id}
    await test_db.commit()

    await handler.handle_lesson_flow(session, "user_reminder", user, conversation, "hello")

    assert len(session.sent) == 1
    assert "QUIZ" in session.sent[0][1]
    assert lesson.title not in session.sent[0][1]


# ---------------------------------------------------------------------------
# Certificate flow — mirrors the whatsapp.py fix: CERTIFICATE is a global
# command reachable from any state, and generates + sends immediately
# instead of the old "being generated" dead end that never actually called
# the generator.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_certificate_name_capture_generates_and_sends_immediately(test_db):
    """Day 7 completion asks for a name; providing one must generate and
    send the certificate right away, not just move to DAY_COMPLETE waiting
    for a second CERTIFICATE message."""
    from app.models.user import User, Language

    handler = KingsChatHandler(settings=Settings(), db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user_legacy_1")
    user.current_day = 7
    user.completed_days = 7
    user.name_confirmed = False
    user.language = Language.ENGLISH
    conversation = await handler.get_or_create_conversation(user.id, "user_legacy_1")
    conversation.current_state = ConversationState.AWAITING_CERTIFICATE_NAME
    await test_db.commit()

    with patch("app.certificates.generator.Minio", return_value=MagicMock()):
        await handler.handle_message(session, "user_legacy_1", "Chidinma Okafor")

    await test_db.refresh(user)
    await test_db.refresh(conversation)
    assert user.name == "Chidinma Okafor"
    assert user.name_confirmed is True
    assert conversation.current_state == ConversationState.PROGRAM_COMPLETE
    final_msg = session.sent[-1][1]
    assert "certificate" in final_msg.lower()
    assert "Chidinma Okafor" in final_msg


@pytest.mark.asyncio
async def test_certificate_command_below_day_seven_declines(test_db):
    """CERTIFICATE from a learner who hasn't finished must not generate anything."""
    handler = KingsChatHandler(settings=Settings(), db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user_not_done")
    user.current_day = 3
    user.completed_days = 2
    conversation = await handler.get_or_create_conversation(user.id, "user_not_done")
    await test_db.commit()

    await handler.handle_message(session, "user_not_done", "CERTIFICATE")

    assert "Day 3/7" in session.sent[-1][1]
    await test_db.refresh(conversation)
    assert conversation.current_state != ConversationState.AWAITING_CERTIFICATE_NAME


@pytest.mark.asyncio
async def test_certificate_command_reaches_legacy_completer_cold(test_db):
    """
    Regression test mirroring test_whatsapp_flow.py's legacy-completer case:
    a learner with completed_days=7, name_confirmed=False, and a stale
    NEW_USER conversation (their prior session already reset) must still
    reach the certificate flow when they text CERTIFICATE cold — the global
    intercept in handle_message must fire before NEW_USER routing sends the
    welcome flow instead.
    """
    from app.models.user import User, Language

    handler = KingsChatHandler(settings=Settings(), db=test_db)
    session = _FakeSession()

    user = await handler.get_or_create_user("user_legacy_2")
    user.name = "KingsChat User"  # legacy placeholder, never replaced
    user.current_day = 7
    user.completed_days = 7
    user.name_confirmed = False
    user.language = Language.ENGLISH
    conversation = await handler.get_or_create_conversation(user.id, "user_legacy_2")
    assert conversation.current_state == ConversationState.NEW_USER
    await test_db.commit()

    await handler.handle_message(session, "user_legacy_2", "CERTIFICATE")

    await test_db.refresh(conversation)
    assert conversation.current_state == ConversationState.AWAITING_CERTIFICATE_NAME
    assert "name" in session.sent[-1][1].lower()

    with patch("app.certificates.generator.Minio", return_value=MagicMock()):
        await handler.handle_message(session, "user_legacy_2", "Bisi Adewale")

    await test_db.refresh(user)
    await test_db.refresh(conversation)
    assert user.name == "Bisi Adewale"
    assert user.name_confirmed is True
    assert conversation.current_state == ConversationState.PROGRAM_COMPLETE
    final_msg = session.sent[-1][1]
    assert "certificate" in final_msg.lower()
    assert "Bisi Adewale" in final_msg


# ---------------------------------------------------------------------------
# Identity-column width (regression for a real bug caught live 2026-07-17:
# users.phone_number etc. were VARCHAR(15), sized for phone numbers, but a
# real KingsChat conversation ID ('kc:' + ~49 chars) is ~52 chars -- Postgres
# rejected every write outright. The in-memory SQLite test DB does NOT
# enforce VARCHAR(n) length at all, so a round-trip test here would pass
# regardless of the column width and prove nothing -- this checks the
# SQLAlchemy column metadata directly instead, which actually regresses if
# someone narrows the column back down.
# ---------------------------------------------------------------------------

def test_identity_columns_wide_enough_for_a_real_conversation_id():
    from app.models.user import User
    from app.models.conversation import Conversation
    from app.models.certificate import Certificate

    # Real ID observed live 2026-07-17; KINGSCHAT_ID_PREFIX adds 'kc:' on top.
    real_id_len = len(KINGSCHAT_ID_PREFIX + "53b9877a73322e5105030100_6a0ae2c1095c473320cb9891")

    for model, column in (
        (User, "phone_number"),
        (Conversation, "phone_number"),
        (Certificate, "learner_phone"),
    ):
        length = model.__table__.columns[column].type.length
        assert length >= real_id_len, (
            f"{model.__name__}.{column} is VARCHAR({length}), too narrow for a "
            f"real KingsChat identity string ({real_id_len} chars) -- this is "
            f"the exact bug that made every KingsChat learner's first message "
            f"fail with StringDataRightTruncationError on Postgres."
        )


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def test_message_builder_quiz_message_is_lettered_plain_text():
    lesson = _quiz_lesson()
    order = [2, 0, 3, 1]
    msg = KingsChatMessageBuilder.build_quiz_message(lesson, 0, order)

    assert "A. " in msg and "B. " in msg and "C. " in msg and "D. " in msg
    assert "Reply with the letter" in msg


def test_message_builder_lesson_message():
    lesson = _quiz_lesson()
    msg = KingsChatMessageBuilder.build_lesson_message(lesson, 1, 5)
    assert "Day 1 - Lesson 1/5" in msg
    assert "Reply QUIZ to start" in msg


def test_message_builder_day_complete_needs_name():
    msg = KingsChatMessageBuilder.build_day_complete_message(7, 5, needs_name=True)
    assert "certificate" in msg.lower()


# ---------------------------------------------------------------------------
# Config: required env vars only enforced when KINGSCHAT_ENABLED=true
# (Architecture Issue 1)
# ---------------------------------------------------------------------------

def test_kingschat_disabled_does_not_require_credentials(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SESSION_SECRET", "y" * 32)
    monkeypatch.delenv("KINGSCHAT_ENABLED", raising=False)
    from app.config import Settings
    # Should not raise -- KingsChat is off by default.
    Settings()


def test_kingschat_enabled_without_credentials_fails_loudly(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SESSION_SECRET", "y" * 32)
    monkeypatch.setenv("KINGSCHAT_ENABLED", "true")
    # setenv("", ...) not delenv: pydantic-settings reads real values for
    # these out of backend/.env (needed for the actual dry-run bot to
    # work), and env vars take precedence over the .env file -- delenv
    # only removes the os.environ override, it doesn't hide the .env
    # file's value, so this test would otherwise silently pass real
    # credentials through and never exercise the "missing" path.
    monkeypatch.setenv("KINGSCHAT_ACCOUNT_EMAIL", "")
    monkeypatch.setenv("KINGSCHAT_ACCOUNT_PASSWORD", "")
    monkeypatch.setenv("KINGSCHAT_SESSION_STORE_PATH", "")
    monkeypatch.setenv("KINGSCHAT_SESSION_ENCRYPTION_KEY", "")
    from app.config import Settings

    with pytest.raises(ValueError, match="KINGSCHAT_ENABLED=true but missing"):
        Settings()


def test_kingschat_enabled_with_all_credentials_succeeds(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("SESSION_SECRET", "y" * 32)
    monkeypatch.setenv("KINGSCHAT_ENABLED", "true")
    monkeypatch.setenv("KINGSCHAT_ACCOUNT_EMAIL", "bot@example.com")
    monkeypatch.setenv("KINGSCHAT_ACCOUNT_PASSWORD", "hunter2")
    monkeypatch.setenv("KINGSCHAT_SESSION_STORE_PATH", "/tmp/kc.session")
    monkeypatch.setenv("KINGSCHAT_SESSION_ENCRYPTION_KEY", _fernet_key())
    from app.config import Settings

    settings = Settings()
    assert settings.KINGSCHAT_ENABLED is True
    assert settings.KINGSCHAT_POOL_SIZE == 10  # default


# ---------------------------------------------------------------------------
# BrowserContext pool (Architecture Issue 2 + Performance Review)
# ---------------------------------------------------------------------------

def _fake_browser(context_factory=None):
    browser = AsyncMock()
    if context_factory is None:
        browser.new_context = AsyncMock(side_effect=lambda **_: AsyncMock())
    else:
        browser.new_context = AsyncMock(side_effect=context_factory)
    return browser


@pytest.mark.asyncio
async def test_pool_rejects_invalid_size():
    with pytest.raises(ValueError):
        KingsChatBrowserPool(pool_size=0)


@pytest.mark.asyncio
async def test_pool_acquire_release_cycles_within_capacity():
    pool = KingsChatBrowserPool(pool_size=2, acquire_timeout_seconds=1.0)
    pool._browser = _fake_browser()  # bypass start(); no real browser needed

    async with pool.acquire() as ctx1:
        assert pool.in_use == 1
        assert ctx1 is not None
    assert pool.in_use == 0

    async with pool.acquire() as ctx2:
        assert pool.in_use == 1
    assert pool.in_use == 0


@pytest.mark.asyncio
async def test_pool_exhaustion_logs_and_eventually_serves(caplog):
    pool = KingsChatBrowserPool(pool_size=1, acquire_timeout_seconds=2.0)
    pool._browser = _fake_browser()

    async with pool.acquire():
        # Pool is now fully occupied (size 1). A concurrent acquire must
        # wait, not raise, and must log the exhaustion per the Performance
        # Review's pool-sizing decision (queue depth + wait time visible).
        async def second_acquire():
            async with pool.acquire():
                pass

        with caplog.at_level("WARNING"):
            task = asyncio.ensure_future(second_acquire())
            await asyncio.sleep(0.05)
            assert pool.waiting == 1

    await task
    assert any("kingschat_pool_exhausted" in r.message for r in caplog.records)
    assert any("kingschat_pool_wait_resolved" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_pool_acquire_timeout_raises_typed_exception():
    pool = KingsChatBrowserPool(pool_size=1, acquire_timeout_seconds=0.1)
    pool._browser = _fake_browser()

    async with pool.acquire():
        with pytest.raises(PoolExhaustedTimeout):
            async with pool.acquire():
                pass


@pytest.mark.asyncio
async def test_pool_passes_proxy_and_storage_state_to_new_context():
    captured = {}

    async def context_factory(**kwargs):
        captured.update(kwargs)
        return AsyncMock()

    pool = KingsChatBrowserPool(
        pool_size=1,
        storage_state={"cookies": []},
        proxy_server="http://proxy.example:8080",
    )
    pool._browser = _fake_browser(context_factory)

    async with pool.acquire():
        pass

    assert captured["storage_state"] == {"cookies": []}
    assert captured["proxy"] == {"server": "http://proxy.example:8080"}


# ---------------------------------------------------------------------------
# send_message — against the real, verified selectors (2026-07-12)
# ---------------------------------------------------------------------------

def _make_page(*, logged_out=False, composer_present=True, send_button_appears=True):
    """Mock Playwright page whose .locator(selector) returns a mock Locator
    keyed by which real selector was asked for, so these tests exercise
    the actual selector constants in kingschat.py rather than duplicating
    them as string literals."""
    page = AsyncMock()

    def locator(selector):
        loc = AsyncMock()
        if selector == SELECTORS.logged_out_redirect_marker:
            loc.count = AsyncMock(return_value=1 if logged_out else 0)
        elif selector == SELECTORS.message_input:
            # send_message waits on editor.first, not a bare .count() check
            # (see send_message's docstring on why) -- mirror that here.
            if composer_present:
                loc.first.wait_for = AsyncMock(return_value=None)
            else:
                loc.first.wait_for = AsyncMock(side_effect=TimeoutError("never appeared"))
        elif selector == SELECTORS.send_button:
            if send_button_appears:
                loc.wait_for = AsyncMock(return_value=None)
            else:
                loc.wait_for = AsyncMock(side_effect=TimeoutError("never appeared"))
        else:
            loc.count = AsyncMock(return_value=0)
        return loc

    page.locator = MagicMock(side_effect=locator)
    return page


@pytest.mark.asyncio
async def test_send_message_happy_path_navigates_types_and_clicks_send():
    page = _make_page()
    session = KingsChatSession(page)

    await session.send_message("conv123", "hello learner")

    # domcontentloaded, not goto()'s default "load" -- see _goto_and_settle's
    # docstring for why (this app never reaches a clean "load" event).
    page.goto.assert_awaited_once_with(
        "https://kingschat.online/conversations/conv123", wait_until="domcontentloaded", timeout=15000
    )
    editor_locator = page.locator(SELECTORS.message_input)
    # locator() is a MagicMock side_effect -- re-invoking it above returns a
    # NEW mock, so assert against the calls actually made on the original
    # objects instead: click/type were called on whatever locator() handed
    # back for message_input during send_message itself.
    assert any(
        call.args == (SELECTORS.message_input,) for call in page.locator.call_args_list
    )
    assert any(
        call.args == (SELECTORS.send_button,) for call in page.locator.call_args_list
    )


@pytest.mark.asyncio
async def test_send_message_never_presses_bare_enter_for_newlines():
    """Regression for the fragmentation bug confirmed live 2026-07-17: the
    old editor.type(text) pressed real Enter for every '\\n', and Enter
    SUBMITS in this Tiptap composer -- the first live lesson went out as
    ~30 separate messages. Newlines must be Shift+Enter soft breaks, and
    the plain Enter key must never be pressed."""
    page = _make_page()
    session = KingsChatSession(page)

    await session.send_message("conv123", "line one\nline two\n\nline four")

    inserted = [c.args[0] for c in page.keyboard.insert_text.await_args_list]
    pressed = [c.args[0] for c in page.keyboard.press.await_args_list]

    assert inserted == ["line one", "line two", "line four"]  # empty line inserts nothing
    assert pressed == ["Shift+Enter"] * 3  # one per '\n', including the blank line
    assert "Enter" not in pressed


@pytest.mark.asyncio
async def test_send_message_raises_ban_detected_when_redirected_to_login():
    page = _make_page(logged_out=True)
    session = KingsChatSession(page)

    with pytest.raises(KingsChatBanDetectedError):
        await session.send_message("conv123", "hello learner")


@pytest.mark.asyncio
async def test_send_message_raises_selector_drift_when_composer_missing():
    page = _make_page(composer_present=False)
    session = KingsChatSession(page)

    with pytest.raises(SelectorDriftError, match="composer"):
        await session.send_message("conv123", "hello learner")


@pytest.mark.asyncio
async def test_send_message_raises_selector_drift_when_send_button_never_appears():
    page = _make_page(send_button_appears=False)
    session = KingsChatSession(page)

    with pytest.raises(SelectorDriftError, match="[Ss]end button"):
        await session.send_message("conv123", "hello learner")


# ---------------------------------------------------------------------------
# contact_filter scoping (--only-contact) — safety mechanism for a first
# live test against a real, actively-used inbox: only touch conversations
# matching the filter, leave everything else completely untouched.
# ---------------------------------------------------------------------------

def _make_inbox_page(rows_spec):
    """Mock page for list_unread_direct_conversation_ids(contact_filter=...).
    rows_spec: list of (visible_text, is_unread) tuples, in DOM order.
    Returns (page, click_log) -- click_log records which row indices were
    actually clicked, so tests can assert non-matching rows were never
    touched.

    Mirrors real KingsChat behavior: clicking a row clears ITS unread state
    for subsequent re-scans (list_unread_direct_conversation_ids loops until
    no more matches), via a mutable unread-flags list rather than a value
    frozen at row-construction time -- without this, a matching row that
    stays "unread" forever after being clicked makes the real while-True
    loop in list_unread_direct_conversation_ids spin forever.
    """
    click_log: list[int] = []
    row_objs = []
    unread_flags = [is_unread for _, is_unread in rows_spec]

    for i, (text, _is_unread) in enumerate(rows_spec):
        row = AsyncMock()
        row.inner_text = AsyncMock(return_value=text)

        def row_locator(selector, _i=i):
            marker = AsyncMock()
            marker.count = AsyncMock(return_value=1 if (unread_flags[_i] and selector == SELECTORS.unread_direct_item) else 0)
            return marker
        row.locator = MagicMock(side_effect=row_locator)

        async def do_click(_i=i):
            click_log.append(_i)
            unread_flags[_i] = False
            page.url = f"https://kingschat.online/conversations/conv_{_i}"
        row.click = AsyncMock(side_effect=do_click)
        row_objs.append(row)

    rows_mock = AsyncMock()
    rows_mock.count = AsyncMock(return_value=len(row_objs))
    rows_mock.nth = MagicMock(side_effect=lambda i: row_objs[i])

    direct_tab = AsyncMock()
    direct_tab.count = AsyncMock(return_value=0)  # skip the "click Direct tab" branch

    def page_locator(selector):
        if selector == SELECTORS.direct_conversation_item:
            return rows_mock
        if selector == "text=Direct":
            return direct_tab
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=0)
        return loc

    page = AsyncMock()
    page.locator = MagicMock(side_effect=page_locator)
    page.url = "https://kingschat.online/conversations"
    return page, click_log


@pytest.mark.asyncio
async def test_contact_filter_only_clicks_matching_unread_row():
    """Two unread rows, only one matches the filter -- the other must never
    be clicked (i.e. never marked read), only inspected read-only."""
    page, click_log = _make_inbox_page([
        ("Jane Real Learner: hey when's day 3?", True),
        ("yomimnair: test message", True),
        ("John Also Real: unrelated unread", True),
    ])
    session = KingsChatSession(page)

    conversation_ids = await session.list_unread_direct_conversation_ids(contact_filter="yomimnair")

    assert conversation_ids == ["conv_1"]
    assert click_log == [1], (
        "only the matching row should ever be clicked -- clicking marks a "
        "conversation read, so touching a non-matching row would incorrectly "
        "clear a real person's unread state"
    )


@pytest.mark.asyncio
async def test_contact_filter_case_insensitive_and_no_match_returns_empty():
    page, click_log = _make_inbox_page([
        ("Someone Else: hi", True),
    ])
    session = KingsChatSession(page)

    conversation_ids = await session.list_unread_direct_conversation_ids(contact_filter="YOMIMNAIR")
    assert conversation_ids == []
    assert click_log == []


@pytest.mark.asyncio
async def test_contact_filter_ignores_read_rows_even_if_text_matches():
    """A row matching the filter text but not carrying the unread marker
    must not be clicked -- filter narrows WHICH unread row to act on, it
    doesn't turn a read conversation into a target."""
    page, click_log = _make_inbox_page([
        ("yomimnair: already read", False),
    ])
    session = KingsChatSession(page)

    conversation_ids = await session.list_unread_direct_conversation_ids(contact_filter="yomimnair")
    assert conversation_ids == []
    assert click_log == []


@pytest.mark.asyncio
async def test_poll_once_passes_contact_filter_through_to_session():
    session = AsyncMock()
    session.detect_ban = AsyncMock(return_value=False)
    session.list_unread_direct_conversation_ids = AsyncMock(return_value=["conv_1"])
    session.read_latest_incoming_message = AsyncMock(return_value="hi")

    handler = AsyncMock(spec=KingsChatHandler)
    ban_fallback = AsyncMock(spec=KingsChatBanFallback)
    watcher = KingsChatWatcher(handler=handler, ban_fallback=ban_fallback)

    await watcher.poll_once(session, contact_filter="yomimnair")

    session.list_unread_direct_conversation_ids.assert_awaited_once_with("yomimnair")


# ---------------------------------------------------------------------------
# Ban detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_ban_true_when_suspension_banner_present():
    page = AsyncMock()

    def locator(selector):
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=1 if selector == SELECTORS.account_suspended_banner else 0)
        return loc

    page.locator = MagicMock(side_effect=locator)
    session = KingsChatSession(page)

    assert await session.detect_ban() is True


@pytest.mark.asyncio
async def test_detect_ban_false_when_no_signals_present():
    page = AsyncMock()
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=0)
    page.locator = MagicMock(return_value=loc)
    session = KingsChatSession(page)

    assert await session.detect_ban() is False


# ---------------------------------------------------------------------------
# Ban fallback (Architecture Issue 3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ban_fallback_skips_send_when_smtp_not_configured(caplog):
    settings = MagicMock()
    settings.SMTP_HOST = None
    settings.ADMIN_EMAIL = "admin@mnair.gov.ng"

    fallback = KingsChatBanFallback(settings)
    with caplog.at_level("ERROR"):
        await fallback.notify_leader(lesson=None, reason="account suspended")

    assert any("kingschat_ban_fallback_undeliverable" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# kingschat_login
# ---------------------------------------------------------------------------

def _make_login_page(*, rejected=False, stuck_on_login_domain=False):
    page = AsyncMock()
    page.url = "https://accounts.kingschat.online/log-in" if stuck_on_login_domain else "https://kingschat.online/conversations"

    locators = {}

    def locator(selector):
        if selector not in locators:
            loc = AsyncMock()
            if selector == SELECTORS.login_error_banner:
                loc.count = AsyncMock(return_value=1 if rejected else 0)
            locators[selector] = loc
        return locators[selector]

    page.locator = MagicMock(side_effect=locator)
    page.context.storage_state = AsyncMock(return_value={"cookies": ["fake"]})
    return page


@pytest.mark.asyncio
async def test_kingschat_login_success_returns_storage_state():
    page = _make_login_page()
    result = await kingschat_login(page, "bot@example.com", "correcthorse")

    page.locator(SELECTORS.login_username_input).fill.assert_awaited_with("bot@example.com")
    page.locator(SELECTORS.login_password_input).fill.assert_awaited_with("correcthorse")
    assert result == {"cookies": ["fake"]}


@pytest.mark.asyncio
async def test_kingschat_login_rejected_credentials_raises():
    page = _make_login_page(rejected=True)
    with pytest.raises(KingsChatLoginError, match="rejected"):
        await kingschat_login(page, "bot@example.com", "wrongpassword")


@pytest.mark.asyncio
async def test_kingschat_login_unexpected_challenge_raises():
    page = _make_login_page(stuck_on_login_domain=True)
    with pytest.raises(KingsChatLoginError, match="CAPTCHA or 2FA"):
        await kingschat_login(page, "bot@example.com", "correcthorse")


# ---------------------------------------------------------------------------
# DryRunKingsChatSession
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_session_logs_instead_of_sending(caplog):
    real_session = AsyncMock(spec=KingsChatSession)
    dry_run = DryRunKingsChatSession(real_session)

    with caplog.at_level("INFO"):
        await dry_run.send_message("conv123", "would-be lesson text")

    real_session.send_message.assert_not_called()
    assert dry_run.sent_log == [("conv123", "would-be lesson text")]
    assert any("kingschat_dry_run_send" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_dry_run_session_delegates_reads_to_real_session():
    real_session = AsyncMock(spec=KingsChatSession)
    real_session.detect_ban = AsyncMock(return_value=True)
    real_session.list_unread_direct_conversation_ids = AsyncMock(return_value=["a", "b"])
    real_session.read_latest_incoming_message = AsyncMock(return_value="hi")

    dry_run = DryRunKingsChatSession(real_session)

    assert await dry_run.detect_ban() is True
    assert await dry_run.list_unread_direct_conversation_ids() == ["a", "b"]
    assert await dry_run.read_latest_incoming_message() == "hi"


# ---------------------------------------------------------------------------
# KingsChatWatcher.poll_once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_once_stops_and_notifies_leader_on_ban():
    session = AsyncMock()
    session.detect_ban = AsyncMock(return_value=True)

    handler = AsyncMock(spec=KingsChatHandler)
    ban_fallback = AsyncMock(spec=KingsChatBanFallback)
    watcher = KingsChatWatcher(handler=handler, ban_fallback=ban_fallback)

    with pytest.raises(KingsChatBanDetectedError):
        await watcher.poll_once(session)

    ban_fallback.notify_leader.assert_awaited_once()
    handler.handle_message.assert_not_called()


@pytest.mark.asyncio
async def test_poll_once_processes_each_unread_conversation():
    session = AsyncMock()
    session.detect_ban = AsyncMock(return_value=False)
    session.list_unread_direct_conversation_ids = AsyncMock(return_value=["conv1", "conv2"])
    session.read_latest_incoming_message = AsyncMock(return_value="QUIZ")

    handler = AsyncMock(spec=KingsChatHandler)
    ban_fallback = AsyncMock(spec=KingsChatBanFallback)
    watcher = KingsChatWatcher(handler=handler, ban_fallback=ban_fallback)

    processed = await watcher.poll_once(session)

    assert processed == 2
    assert handler.handle_message.await_count == 2
    handler.handle_message.assert_any_await(session, "conv1", "QUIZ")
    handler.handle_message.assert_any_await(session, "conv2", "QUIZ")


@pytest.mark.asyncio
async def test_poll_once_skips_conversation_with_no_incoming_message_found(caplog):
    """An unread marker with no readable non-outgoing message is logged,
    not silently dropped or crashed on -- this is exactly the kind of
    'unread flag present but nothing to act on' edge case a real chat UI
    can produce (e.g. a reaction-only update)."""
    session = AsyncMock()
    session.detect_ban = AsyncMock(return_value=False)
    session.list_unread_direct_conversation_ids = AsyncMock(return_value=["conv1"])
    session.read_latest_incoming_message = AsyncMock(return_value=None)

    handler = AsyncMock(spec=KingsChatHandler)
    ban_fallback = AsyncMock(spec=KingsChatBanFallback)
    watcher = KingsChatWatcher(handler=handler, ban_fallback=ban_fallback)

    with caplog.at_level("WARNING"):
        processed = await watcher.poll_once(session)

    assert processed == 0
    handler.handle_message.assert_not_called()
    assert any("kingschat_no_incoming_message_found" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Browser pool: set_storage_state (needed since login happens after pool
# construction -- see kingschat_bot.py's ensure_logged_in)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pool_set_storage_state_applied_to_new_contexts():
    captured = {}

    async def context_factory(**kwargs):
        captured.update(kwargs)
        return AsyncMock()

    pool = KingsChatBrowserPool(pool_size=1)
    pool._browser = _fake_browser(context_factory)

    pool.set_storage_state({"cookies": ["from-login"]})

    async with pool.acquire():
        pass

    assert captured["storage_state"] == {"cookies": ["from-login"]}


# ---------------------------------------------------------------------------
# Session identity verification (regression for the wrong-account bug found
# live 2026-07-17: the stored session belonged to the founder's personal
# account, not the bot's, and every "bot" reply went out as the founder --
# ensure_logged_in only ever checked that the session worked, never whose
# it was)
# ---------------------------------------------------------------------------

from app.channels.kingschat import get_logged_in_username


def _page_with_profile_link(handle):
    page = AsyncMock()

    def locator(selector):
        loc = AsyncMock()
        if selector == "a[href^='/user/']" and handle is not None:
            loc.first.wait_for = AsyncMock(return_value=None)
            loc.first.get_attribute = AsyncMock(return_value=f"/user/{handle}")
        else:
            loc.first.wait_for = AsyncMock(side_effect=TimeoutError("no profile link"))
        return loc

    page.locator = MagicMock(side_effect=locator)
    page.url = "https://kingschat.online/conversations"
    return page


@pytest.mark.asyncio
async def test_get_logged_in_username_reads_profile_link():
    page = _page_with_profile_link("yomimnair")
    assert await get_logged_in_username(page) == "yomimnair"


@pytest.mark.asyncio
async def test_get_logged_in_username_returns_none_when_link_never_renders():
    page = _page_with_profile_link(None)
    assert await get_logged_in_username(page) is None


@pytest.mark.asyncio
async def test_ensure_logged_in_discards_wrong_account_session(monkeypatch, tmp_path):
    """A stored session that WORKS but belongs to the wrong account must be
    discarded and replaced via fresh login -- not silently used. This is
    the exact bug from the first live test."""
    import kingschat_bot as bot_mod
    from contextlib import asynccontextmanager

    store = KingsChatSessionStore(
        path=str(tmp_path / "kc.session"), encryption_key=_fernet_key()
    )
    store.save({"cookies": [{"name": "who", "value": "wrong-account"}]})

    handles = iter(["dcnyomi", "yomimnair"])  # stored session, then fresh login

    async def fake_get_username(page):
        return next(handles)

    async def fake_goto(page, url, **kw):
        pass

    async def fake_login(page, email, password):
        return {"cookies": [{"name": "who", "value": "right-account"}]}

    monkeypatch.setattr(bot_mod, "get_logged_in_username", fake_get_username)
    monkeypatch.setattr(bot_mod, "_goto_and_settle", fake_goto)
    monkeypatch.setattr(bot_mod, "kingschat_login", fake_login)

    page = AsyncMock()
    page.url = "https://kingschat.online/conversations"
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    class FakePool:
        def set_storage_state(self, s):
            pass

        @asynccontextmanager
        async def acquire(self):
            yield context

    class FakeSettings:
        KINGSCHAT_EXPECTED_USERNAME = "yomimnair"
        KINGSCHAT_ACCOUNT_EMAIL = "bot@example.com"
        KINGSCHAT_ACCOUNT_PASSWORD = "pw"

    result = await bot_mod.ensure_logged_in(FakePool(), store, FakeSettings())

    assert result == {"cookies": [{"name": "who", "value": "right-account"}]}
    # The wrong-account session must have been replaced on disk too
    assert store.load() == {"cookies": [{"name": "who", "value": "right-account"}]}


@pytest.mark.asyncio
async def test_ensure_logged_in_hard_fails_when_credentials_are_wrong_account(monkeypatch, tmp_path):
    """If even a FRESH login lands on the wrong account, the credentials
    themselves are wrong -- hard failure, and the wrong session must NOT
    be saved."""
    import kingschat_bot as bot_mod
    from contextlib import asynccontextmanager

    store = KingsChatSessionStore(
        path=str(tmp_path / "kc.session"), encryption_key=_fernet_key()
    )

    async def fake_get_username(page):
        return "dcnyomi"  # always the wrong account

    async def fake_goto(page, url, **kw):
        pass

    async def fake_login(page, email, password):
        return {"cookies": [{"name": "who", "value": "wrong-account"}]}

    monkeypatch.setattr(bot_mod, "get_logged_in_username", fake_get_username)
    monkeypatch.setattr(bot_mod, "_goto_and_settle", fake_goto)
    monkeypatch.setattr(bot_mod, "kingschat_login", fake_login)

    page = AsyncMock()
    page.url = "https://kingschat.online/conversations"
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    class FakePool:
        def set_storage_state(self, s):
            pass

        @asynccontextmanager
        async def acquire(self):
            yield context

    class FakeSettings:
        KINGSCHAT_EXPECTED_USERNAME = "yomimnair"
        KINGSCHAT_ACCOUNT_EMAIL = "bot@example.com"
        KINGSCHAT_ACCOUNT_PASSWORD = "pw"

    with pytest.raises(KingsChatLoginError, match="WRONG account"):
        await bot_mod.ensure_logged_in(FakePool(), store, FakeSettings())

    assert store.load() is None  # wrong-account session never persisted
