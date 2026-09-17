"""
ConversationEngine tests — the channel-agnostic 7-day flow.

Ported from the retired test_whatsapp_flow.py: same scenarios, but the
assertions are on the OutboundMessage list the engine returns instead of
on captured Meta API payloads.
"""

import pytest
from sqlalchemy import select

from app.config import Settings
from app.engine import ConversationEngine, MessageBuilder, get_or_create_conversation, get_or_create_learner
from app.engine.messages import button_ids
from app.models.conversation import Conversation, ConversationChannel, ConversationState
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.user import Language, User


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

TOPICS = ["what_is_ai", "how_ai_works", "ai_in_nigeria", "ai_tools", "ai_ethics"]


def make_lesson(day: int, topic: str, lang: str = "en", correct: int = 0) -> Lesson:
    return Lesson(
        lesson_id=f"d{day}_{topic}_{lang}",
        day=day,
        topic=topic,
        language=lang,
        title=f"Day {day} {topic}",
        content=f"Content for {topic} on day {day}.",
        word_count=6,
        quiz=[{"question": f"Q{i}", "options": ["Right", "Wrong 1", "Wrong 2", "Wrong 3"], "correct": correct} for i in range(5)],
    )


async def seed_days(db, days=(1,), lang="en"):
    for day in days:
        for topic in TOPICS:
            db.add(make_lesson(day, topic, lang))
    await db.commit()


async def fresh_engine(db, identity="tg:1001", channel=ConversationChannel.TELEGRAM):
    settings = Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t")
    user = await get_or_create_learner(db, identity, channel, telegram_chat_id="1001" if channel == ConversationChannel.TELEGRAM else None)
    conversation = await get_or_create_conversation(db, user, channel)
    return ConversationEngine(db, settings), user, conversation


async def answer_all_correct(engine, user, conversation, quiz_msg):
    """Answer 5 questions choosing the button whose description is 'Right'."""
    replies = [quiz_msg]
    for _ in range(5):
        current = replies[-1]
        assert current.kind == "quiz", current.text
        right = next(b for b in current.buttons if b.description == "Right")
        replies = await engine.handle(user, conversation, interactive_id=right.id)
    return replies


async def complete_day(engine, user, conversation, first_lesson_reply):
    """Given the first lesson message of a day, pass all 5 quizzes."""
    reply = first_lesson_reply
    for _ in range(5):
        assert reply.kind == "lesson", reply.text
        quiz_replies = await engine.handle(user, conversation, interactive_id="quiz")
        replies = await answer_all_correct(engine, user, conversation, quiz_replies[0])
        # result message, then either the next lesson or the day-complete message
        assert replies[0].kind == "result" and replies[0].meta["passed"]
        reply = replies[1]
    return reply


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_builder_welcome_and_language(test_db):
    msg = MessageBuilder.build_welcome_message()
    assert "Welcome to Make Nigeria AI Ready" in msg.text
    assert "Hello Chidi!" in MessageBuilder.build_welcome_message("Chidi").text

    lang = MessageBuilder.build_language_selector()
    assert button_ids(lang) == ["lang_en", "lang_pid", "lang_ha", "lang_yo", "lang_ig"]


@pytest.mark.asyncio
async def test_builder_quiz_honours_shuffle(test_db):
    lesson = make_lesson(1, "what_is_ai")
    lesson.quiz[0]["options"] = ["A. Artificial Intelligence", "B. Automated Internet", "C. Advanced Info", "D. None"]
    order = [2, 0, 3, 1]
    msg = MessageBuilder.build_quiz_message(lesson, 0, order)
    assert msg.kind == "quiz"
    assert "Question 1/5" in msg.text
    assert [b.id for b in msg.buttons] == ["ans_0_0", "ans_0_1", "ans_0_2", "ans_0_3"]
    # embedded letter prefixes stripped, display order honoured
    assert [b.description for b in msg.buttons] == ["Advanced Info", "Artificial Intelligence", "None", "Automated Internet"]
    assert "A. Advanced Info" in msg.text


@pytest.mark.asyncio
async def test_builder_reminder_all_languages(test_db):
    for lang in Language:
        msg = MessageBuilder.build_reminder_message(lang, 3, 4)
        assert "3" in msg.text and "4" in msg.text
        assert button_ids(msg) == ["continue_learning"]
    assert "1 day " in MessageBuilder.build_reminder_message(Language.ENGLISH, 6, 1).text


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_learner_idempotent(test_db):
    u1 = await get_or_create_learner(test_db, "tg:42", ConversationChannel.TELEGRAM, telegram_chat_id="42")
    u2 = await get_or_create_learner(test_db, "tg:42", ConversationChannel.TELEGRAM, telegram_chat_id="42")
    assert u1.id == u2.id
    assert u1.preferred_channel == "telegram"
    assert u1.telegram_chat_id == "42"
    assert u1.name == "Telegram User"

    c1 = await get_or_create_conversation(test_db, u1, ConversationChannel.TELEGRAM)
    c2 = await get_or_create_conversation(test_db, u1, ConversationChannel.TELEGRAM)
    assert c1.id == c2.id
    assert c1.current_state == ConversationState.NEW_USER


# ---------------------------------------------------------------------------
# flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_user_gets_welcome_and_language_prompt(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)

    replies = await engine.handle(user, conv, "hi")
    assert [m.kind for m in replies] == ["text", "choice"]
    assert conv.current_state == ConversationState.AWAITING_LANGUAGE
    assert user.last_active_at is not None
    # history recorded for the web thread
    assert [h["role"] for h in conv.message_history] == ["user", "bot", "bot"]


@pytest.mark.asyncio
async def test_language_selection_delivers_first_lesson(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")

    replies = await engine.handle(user, conv, interactive_id="lang_en")
    assert user.language == Language.ENGLISH
    assert conv.current_state == ConversationState.IN_LESSON
    assert replies[0].kind == "lesson"
    assert "Day 1 - Lesson 1/5" in replies[0].text
    assert button_ids(replies[0]) == ["quiz"]
    assert conv.context["current_lesson_id"] == replies[0].meta["lesson_id"]


@pytest.mark.asyncio
async def test_typed_language_name_works_like_button(test_db):
    await seed_days(test_db, lang="pid")
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    replies = await engine.handle(user, conv, "Pidgin")
    assert user.language == Language.PIDGIN
    assert replies[0].kind == "lesson"


@pytest.mark.asyncio
async def test_invalid_language_reprompts(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    replies = await engine.handle(user, conv, "klingon")
    assert replies[0].kind == "choice"
    assert conv.current_state == ConversationState.AWAITING_LANGUAGE


@pytest.mark.asyncio
async def test_full_lesson_quiz_pass_moves_on(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    lesson = (await engine.handle(user, conv, interactive_id="lang_en"))[0]
    first_lesson_id = lesson.meta["lesson_id"]

    quiz = (await engine.handle(user, conv, interactive_id="quiz"))[0]
    assert conv.current_state == ConversationState.AWAITING_QUIZ
    assert quiz.meta["question"] == 0

    replies = await answer_all_correct(engine, user, conv, quiz)
    assert replies[0].kind == "result" and replies[0].meta["passed"]
    assert "100%" in replies[0].text
    assert replies[1].kind == "lesson"
    assert "Lesson 2/5" in replies[1].text
    assert conv.current_state == ConversationState.IN_LESSON

    progress = (await test_db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == first_lesson_id)
    )).scalar_one()
    assert progress.is_completed


@pytest.mark.asyncio
async def test_typed_letter_answers_work(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    await engine.handle(user, conv, interactive_id="lang_en")
    quiz = (await engine.handle(user, conv, "quiz"))[0]

    replies = [quiz]
    for _ in range(5):
        current = replies[-1]
        pos = next(i for i, b in enumerate(current.buttons) if b.description == "Right")
        replies = await engine.handle(user, conv, chr(65 + pos))
    assert replies[0].meta["passed"]


@pytest.mark.asyncio
async def test_quiz_fail_offers_retry_and_reshuffles(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    lesson = (await engine.handle(user, conv, interactive_id="lang_en"))[0]
    quiz = (await engine.handle(user, conv, interactive_id="quiz"))[0]

    replies = [quiz]
    for _ in range(5):
        wrong = next(b for b in replies[-1].buttons if b.description != "Right")
        replies = await engine.handle(user, conv, interactive_id=wrong.id)

    result = replies[0]
    assert result.kind == "result" and not result.meta["passed"]
    assert button_ids(result) == ["retry"]
    assert conv.current_state == ConversationState.IN_LESSON
    assert conv.context == {"current_lesson_id": lesson.meta["lesson_id"]}

    retry = (await engine.handle(user, conv, interactive_id="retry"))[0]
    assert retry.kind == "quiz" and retry.meta["question"] == 0
    assert retry.meta["lesson_id"] == lesson.meta["lesson_id"]


@pytest.mark.asyncio
async def test_non_answer_during_quiz_resends_same_question_same_order(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    await engine.handle(user, conv, interactive_id="lang_en")
    quiz = (await engine.handle(user, conv, interactive_id="quiz"))[0]

    again = (await engine.handle(user, conv, "what?"))[0]
    assert again.kind == "quiz"
    assert [b.description for b in again.buttons] == [b.description for b in quiz.buttons]


@pytest.mark.asyncio
async def test_continue_resends_current_step(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    lesson = (await engine.handle(user, conv, interactive_id="lang_en"))[0]

    resumed = (await engine.handle(user, conv, interactive_id="continue_learning"))[0]
    assert resumed.kind == "lesson" and resumed.meta["lesson_id"] == lesson.meta["lesson_id"]

    quiz = (await engine.handle(user, conv, "QUIZ"))[0]
    resumed_quiz = (await engine.handle(user, conv, "continue"))[0]
    assert resumed_quiz.kind == "quiz"
    assert [b.description for b in resumed_quiz.buttons] == [b.description for b in quiz.buttons]


@pytest.mark.asyncio
async def test_day_completion_then_next_day(test_db):
    await seed_days(test_db, days=(1, 2))
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    first = (await engine.handle(user, conv, interactive_id="lang_en"))[0]

    done = await complete_day(engine, user, conv, first)
    assert "DAY 1 COMPLETE" in done.text
    assert button_ids(done) == ["next"]
    assert conv.current_state == ConversationState.DAY_COMPLETE
    await test_db.refresh(user)
    assert user.completed_days == 1

    # Anything but NEXT nags with the button
    nag = (await engine.handle(user, conv, "hello"))[0]
    assert button_ids(nag) == ["next"]

    day2 = (await engine.handle(user, conv, interactive_id="next"))[0]
    assert day2.kind == "lesson" and "Day 2 - Lesson 1/5" in day2.text
    await test_db.refresh(user)
    assert user.current_day == 2


@pytest.mark.asyncio
async def test_certificate_blocked_before_day_seven(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    await engine.handle(user, conv, interactive_id="lang_en")
    reply = (await engine.handle(user, conv, "CERTIFICATE"))[0]
    assert "finish all 7 days" in reply.text
    assert conv.current_state == ConversationState.IN_LESSON


@pytest.mark.asyncio
async def test_day_seven_asks_for_name_then_issues_certificate(test_db, monkeypatch):
    await seed_days(test_db, days=tuple(range(1, 8)))
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    reply = (await engine.handle(user, conv, interactive_id="lang_en"))[0]

    for day in range(1, 8):
        done = await complete_day(engine, user, conv, reply)
        if day < 7:
            reply = (await engine.handle(user, conv, interactive_id="next"))[0]

    assert "COURSE COMPLETE" in done.text
    assert done.meta["needs_name"] is True
    assert conv.current_state == ConversationState.AWAITING_CERTIFICATE_NAME
    await test_db.refresh(user)
    assert user.completed_days == 7

    # Reserved words are rejected as names
    bad = (await engine.handle(user, conv, "next"))[0]
    assert "full name" in bad.text
    assert user.name_confirmed is False

    class FakeCert:
        certificate_id = "MNAIR-2026-1-ABCD"

    async def fake_generate(self, user_id, language):
        return FakeCert()

    from app.certificates.generator import CertificateGenerator
    # The real constructor opens a MinIO connection; keep the test offline
    monkeypatch.setattr(CertificateGenerator, "__init__", lambda self, db, settings: None)
    monkeypatch.setattr(CertificateGenerator, "generate_and_store_certificate", fake_generate)

    replies = await engine.handle(user, conv, "Adaeze Okafor")
    assert user.name == "Adaeze Okafor" and user.name_confirmed
    assert replies[-1].kind == "certificate"
    assert "MNAIR-2026-1-ABCD" in replies[-1].text
    assert "/verify?code=MNAIR-2026-1-ABCD&name=Adaeze%20Okafor" in replies[-1].meta["url"]
    assert conv.current_state == ConversationState.PROGRAM_COMPLETE

    # CERTIFICATE from PROGRAM_COMPLETE re-sends the link (idempotent)
    again = (await engine.handle(user, conv, interactive_id="certificate"))[0]
    assert again.kind == "certificate"


@pytest.mark.asyncio
async def test_certificate_cold_from_new_conversation_for_legacy_completer(test_db, monkeypatch):
    """A learner who finished before names were collected texts CERTIFICATE
    from a brand-new conversation and is asked for a name."""
    engine, user, conv = await fresh_engine(test_db)
    user.completed_days = 7
    user.current_day = 7
    user.name_confirmed = False
    await test_db.commit()

    reply = (await engine.handle(user, conv, "certificate"))[0]
    assert "eligible" in reply.text
    assert conv.current_state == ConversationState.AWAITING_CERTIFICATE_NAME


@pytest.mark.asyncio
async def test_language_change_mid_course_requires_confirmation(test_db):
    await seed_days(test_db, days=(1,), lang="en")
    await seed_days(test_db, days=(1,), lang="ha")
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    lesson = (await engine.handle(user, conv, interactive_id="lang_en"))[0]
    # make some progress so the confirmation is required
    quiz = (await engine.handle(user, conv, interactive_id="quiz"))[0]
    await answer_all_correct(engine, user, conv, quiz)

    selector = (await engine.handle(user, conv, "LANGUAGE"))[0]
    assert selector.kind == "choice"
    confirm = (await engine.handle(user, conv, interactive_id="lang_ha"))[0]
    assert "Switching to Hausa" in confirm.text
    assert button_ids(confirm) == ["yes", "no"]

    cancelled = (await engine.handle(user, conv, interactive_id="no"))[0]
    assert "cancelled" in cancelled.text
    assert user.language == Language.ENGLISH
    assert conv.current_state == ConversationState.IN_LESSON
    assert conv.context.get("current_lesson_id") is not None

    await engine.handle(user, conv, "LANGUAGE")
    await engine.handle(user, conv, interactive_id="lang_ha")
    switched = (await engine.handle(user, conv, "yes"))[0]
    assert user.language == Language.HAUSA
    assert switched.kind == "lesson"


@pytest.mark.asyncio
async def test_progress_command(test_db):
    await seed_days(test_db)
    engine, user, conv = await fresh_engine(test_db)
    await engine.handle(user, conv, "hi")
    await engine.handle(user, conv, interactive_id="lang_en")
    reply = (await engine.handle(user, conv, "progress"))[0]
    assert "Your Progress" in reply.text
    assert conv.current_state == ConversationState.IN_LESSON


@pytest.mark.asyncio
async def test_web_and_telegram_share_the_same_learner_progress_model(test_db):
    """Two channels, one engine: a web learner's conversation is separate
    from a Telegram learner's, but both run the identical flow."""
    await seed_days(test_db)
    engine_web, web_user, web_conv = await fresh_engine(test_db, identity="+2348031234567", channel=ConversationChannel.WEB)
    engine_tg, tg_user, tg_conv = await fresh_engine(test_db)

    assert web_user.id != tg_user.id
    web_first = (await engine_web.handle(web_user, web_conv, "start"))
    tg_first = (await engine_tg.handle(tg_user, tg_conv, "/start"))
    assert [m.kind for m in web_first] == [m.kind for m in tg_first] == ["text", "choice"]
    assert web_conv.channel == ConversationChannel.WEB
    assert tg_conv.channel == ConversationChannel.TELEGRAM
