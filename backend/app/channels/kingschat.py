"""
KingsChat Channel Handler for MNAIR Platform.

Delivers the same 7-day curriculum as whatsapp.py/ussd.py/sms.py, but over
KingsChat instead — reused per Premise 2 of the KingsChat design doc
(~/.gstack/projects/yomisys-mnair/yomis-master-design-20260712-032947.md):
only the channel adapter is new, curriculum/grading/backend are untouched.

WHY THIS FILE LOOKS DIFFERENT FROM whatsapp.py: KingsChat has no confirmed
bot/webhook API (verified by direct prior experience — see the design doc's
Premise 1). This adapter drives a real KingsChat web session via Playwright
browser automation instead of receiving webhooks. That is a fundamentally
different transport shape (long-running watched session vs. stateless
HTTP-in/HTTP-out), which is exactly why /plan-eng-review's cross-model
review reversed the original plan to unify this with whatsapp.py/ussd.py
under one shared interface — see that review's Code Quality Issue 1
reversal. This module is intentionally standalone.

SELECTORS VERIFIED 2026-07-12 against the live kingschat.online web app
(Vue 3 SPA, BEM-style scoped class names, no data-testid attributes
anywhere — every selector below is a real class name, not a guess).
Verified via the `browse` skill against the founder's own account:
navigated the login flow, opened both a group and a 1:1 conversation, and
inspected the DOM directly (`js`/`attrs` commands), not by reading visible
text. Two things confirmed live and NOT just inferred from class names:
  - The send button (`TextEditorButtons__button-send`) does not exist in
    the DOM until the composer has content — confirmed by typing text
    into the real composer and re-querying.
  - The "sent by me" modifier (`ChatMessage__main-container--actor`) was
    cross-checked against message content in a real DM thread: bubbles
    without `--actor` matched the other party's name, bubbles with it
    didn't.
No message was actually sent during verification — the composer was
cleared via execCommand before navigating away, never submitted.

One thing NOT verified live (see kingschat.py's TODOS.md P0 spike, and the
note on `KingsChatSession.send_message` below): whether pressing Enter in
this Tiptap/ProseMirror editor sends the message or inserts a newline.
Testing that against a real ministry conversation thread risked posting a
malformed partial message into it, so `send_message` drives the composer
via the confirmed click-based Send button instead of Enter, and multi-line
lesson text should get a dedicated test (in a disposable test
conversation, not a real thread) before this handles production traffic.

Navigation model: there is no separate "user ID" distinct from the
conversation — KingsChat's URLs are `/conversations/{conversation_id}`,
and that's the one identifier this adapter needs per learner. The
`kingschat_user_id` parameter name used throughout this file is really
functioning as that conversation ID; kept as `kingschat_user_id` to match
the identity-slot naming already used in `app.models.user` rather than
introduce a second name for the same concept.

Because this is someone else's frontend with no API contract, these class
names can drift on any KingsChat deploy with no notice — this is exactly
the kind of silent breakage Open Question 7 (failure-mode detection) in
the design doc is about. `KingsChatSession.detect_ban()` catches account-
level failures; a UI-drift break (selectors stop matching) is a different
failure mode this file doesn't yet detect and should before relying on it
unattended — flag any selector `count() == 0` where content was expected,
not just the ban signals already checked.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.conversation import Conversation, ConversationChannel, ConversationState
from app.models.lesson import Lesson
from app.models.user import Language, User
from app.services.kingschat_browser_pool import KingsChatBrowserPool, PoolExhaustedTimeout
from app.services.kingschat_session_store import KingsChatSessionStore, SessionStoreError
from app.services.lesson_state import LessonStateManager
from app.services.quiz_shuffle import get_or_create_shuffle, shuffled_options, unshuffle_answer

logger = logging.getLogger(__name__)

# KingsChat learner identity is stored in User.phone_number with this
# prefix (see the field's docstring in app/models/user.py) since KingsChat
# has no phone-number-based identity in this flow, unlike WhatsApp/USSD/SMS.
KINGSCHAT_ID_PREFIX = "kc:"


class KingsChatBanDetectedError(Exception):
    """Raised when the automated session detects the account has been
    suspended, logged out unexpectedly, or is showing a CAPTCHA/anti-bot
    challenge it can't solve. Callers (the polling loop) catch this and
    trigger the leader-notification fallback — see KingsChatBanFallback."""


@dataclass(frozen=True)
class KingsChatSelectors:
    """Verified 2026-07-12 against the live kingschat.online web app — see
    this module's docstring for exactly what was and wasn't confirmed
    live. The two ban/anti-bot selectors below are the one part NOT
    verified against a real signal (the test account was never actually
    suspended) — they're a best-effort guess at likely markup and should
    be treated with the same suspicion the rest of this file no longer
    needs.
    """
    login_username_input: str = "#usernameOrEmail"
    login_password_input: str = "#password"
    login_submit_button: str = "button[type='submit']"
    # Appears as aria-describedby="password-error" on the password field
    # plus a border-red-500 class, once login fails.
    login_error_banner: str = "#password-error"

    # Inbox / thread list. Direct (1:1) vs Groups are separate filter tabs
    # in the UI itself ("Direct 12" / "Groups 75") — confirms Open
    # Question 5's premise that these are different UI surfaces, not just
    # different Playwright problems.
    direct_conversation_item: str = ".PrivateConversationBox__main-container"
    unread_direct_item: str = ".PrivateConversationBox__last-message--unread"
    unread_group_item: str = ".GroupConversationBox__last-message--unread"

    # Message thread. Conversation identity is the URL path
    # (/conversations/{id}), not a separate DOM attribute — see this
    # module's docstring.
    messages_list: str = ".Chat__messages-list"
    message_bubble: str = ".ChatMessage__main-container"
    # Modifier class present only on messages sent BY this account —
    # cross-checked live against message content, not inferred from the
    # name alone.
    message_bubble_outgoing_modifier: str = "ChatMessage__main-container--actor"
    message_text: str = ".ChatMessageText__main-container"
    # KingsChat's own "SuperUser" (verified business/org account) concept
    # from the design doc's Open Question 3 shows up here as a modifier —
    # confirms it's a real, DOM-visible distinction, not just a badge.
    message_bubble_superuser_modifier: str = "ChatMessage__main-container--superuser-post"

    # Composer: a Tiptap/ProseMirror contenteditable div, not a plain
    # <textarea> — confirmed live (`fill` on a CSS selector would not have
    # worked here; this needs click + type).
    message_input: str = ".tiptap.ProseMirror"
    # Does not exist in the DOM until the composer has content — confirmed
    # live by typing into the real composer and re-querying. Never query
    # this before typing; it will correctly find nothing.
    send_button: str = ".TextEditorButtons__button-send"

    # Ban / anti-bot detection signals — NOT verified against a real
    # suspension (the test account was never actually banned). Best-effort
    # guess at likely markup; treat with real suspicion until an actual
    # ban event confirms or corrects these.
    account_suspended_banner: str = "[class*='Suspended'], [class*='AccountBanned']"
    captcha_challenge: str = "iframe[title*='captcha' i], iframe[src*='recaptcha' i]"
    # Same selector as the login form — if this exists on a page where the
    # bot expected to already be authenticated, the session expired/was
    # invalidated server-side.
    logged_out_redirect_marker: str = "#usernameOrEmail"


SELECTORS = KingsChatSelectors()


class KingsChatMessageBuilder:
    """Builds plain-text messages for KingsChat.

    Unlike WhatsApp's interactive buttons/lists, this adapter types and
    reads plain text through a browser session — there is no reliable way
    to drive KingsChat's native rich-UI components (if any exist) through
    generic automation, so quiz options are rendered as a lettered list and
    the learner replies with a letter. This is a deliberate simplification,
    not an oversight: fewer moving parts in the one layer of this system
    that has no official API to fall back on if something breaks.
    """

    @staticmethod
    def build_welcome_message() -> str:
        return (
            "🎓 Welcome to Make Nigeria AI Ready (MNAIR)!\n\n"
            "Learn Artificial Intelligence in 7 days — for FREE!\n\n"
            "📱 Study at your own pace\n"
            "🎯 5 topics per day\n"
            "📜 Get a certificate when you finish\n\n"
            "Reply with a number to choose your language:\n"
            "1. English\n2. Pidgin\n3. Hausa\n4. Yoruba\n5. Igbo"
        )

    @staticmethod
    def build_lesson_message(lesson: Lesson, lesson_number: int, total: int = 5) -> str:
        return (
            f"📚 Day {lesson.day} - Lesson {lesson_number}/{total}\n"
            f"{'=' * 30}\n\n"
            f"{lesson.title}\n\n"
            f"{lesson.content}\n\n"
            f"{'=' * 30}\n"
            f"Ready for the quiz? Reply QUIZ to start!"
        )

    @staticmethod
    def build_quiz_message(lesson: Lesson, question_num: int, order: list[int]) -> str:
        if not lesson.quiz or question_num >= len(lesson.quiz):
            raise ValueError(f"Invalid question number {question_num}")

        quiz_item = lesson.quiz[question_num]
        options = shuffled_options(quiz_item["options"], order)
        lettered = "\n".join(f"{chr(65 + i)}. {opt}" for i, opt in enumerate(options))

        return (
            f"❓ Question {question_num + 1}/5\n\n"
            f"{quiz_item['question']}\n\n"
            f"{lettered}\n\n"
            f"Reply with the letter of your answer (A, B, C, or D)."
        )

    @staticmethod
    def build_quiz_result_message(score: float, passed: bool, attempt: int, can_retry: bool) -> str:
        if passed:
            return (
                f"🎉 Congratulations!\n\n"
                f"You scored {score:.0f}% on your quiz!\n"
                f"Attempt: {attempt}/3\n\n"
                f"✅ Lesson completed! Moving to next lesson..."
            )
        retry_msg = "\n\nReply RETRY to try again!" if can_retry else "\n\n❌ Maximum attempts reached."
        return (
            f"😔 Not quite there yet\n\n"
            f"You scored {score:.0f}%\n"
            f"You need 60% to pass (3/5 correct)\n"
            f"Attempt: {attempt}/3"
            f"{retry_msg}"
        )

    @staticmethod
    def build_day_complete_message(day: int, lessons_completed: int, needs_name: bool = False) -> str:
        if day < 7:
            cta = f"Reply NEXT to continue to Day {day + 1}!"
        elif needs_name:
            cta = "What name should appear on your certificate? Reply with your full name."
        else:
            cta = "Reply CERTIFICATE to get your certificate!"

        return (
            f"🎊 DAY {day} COMPLETE! 🎊\n\n"
            f"Congratulations! You've finished all {lessons_completed} lessons for Day {day}!\n\n"
            f"{'🏆 Keep going!' if day < 7 else '🎓 COURSE COMPLETE!'}\n\n"
            f"{cta}"
        )


class KingsChatBanFallback:
    """On ban/suspension detection, the KingsChat channel itself can't be
    used to notify anyone — it's the thing that's down. This sends an email
    (reusing the existing SMTP settings already in app.config, unrelated to
    KingsChat) to the leader/admin with a manual-share message they can post
    themselves, degrading gracefully instead of the channel going silently
    dark. This is the fallback mechanism locked in during /plan-eng-review's
    Architecture Issue 3 — it deliberately reuses the "manual pilot"
    mechanism (Approach C from the original design doc) as a safety net
    only, not as the primary path.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def notify_leader(self, lesson: Optional[Lesson], reason: str) -> None:
        import smtplib
        from email.mime.text import MIMEText

        if not self.settings.SMTP_HOST or not self.settings.ADMIN_EMAIL:
            logger.error(
                "kingschat_ban_fallback_undeliverable reason=%s "
                "(SMTP_HOST or ADMIN_EMAIL not configured — fallback "
                "notification could not be sent)",
                reason,
            )
            return

        body = (
            f"The MNAIR KingsChat bot has stopped working: {reason}\n\n"
            f"Please manually share today's lesson with the group until this "
            f"is fixed:\n\n"
        )
        if lesson is not None:
            body += f"---\n{lesson.title}\n\n{lesson.content}\n---\n\n"
        body += f"Sign up for the full course at {self.settings.FRONTEND_URL}"

        msg = MIMEText(body)
        msg["Subject"] = "[MNAIR] KingsChat bot is down — manual share needed"
        msg["From"] = self.settings.SMTP_FROM_EMAIL
        msg["To"] = self.settings.ADMIN_EMAIL

        try:
            with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT) as server:
                if self.settings.SMTP_USERNAME and self.settings.SMTP_PASSWORD:
                    server.starttls()
                    server.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD)
                server.send_message(msg)
            logger.info("kingschat_ban_fallback_sent reason=%s", reason)
        except OSError:
            logger.exception("kingschat_ban_fallback_send_failed reason=%s", reason)


class KingsChatHandler:
    """Mirrors WhatsAppWebhookHandler's state machine — same
    ConversationState transitions, same LessonStateManager/quiz_shuffle
    calls — with sending done via a Playwright page instead of an HTTP
    call, and no inbound webhook (see KingsChatWatcher for how incoming
    messages actually reach this handler).
    """

    def __init__(self, settings: Settings, db: AsyncSession):
        self.settings = settings
        self.db = db
        self.message_builder = KingsChatMessageBuilder()
        self.lesson_manager = LessonStateManager(db)

    @staticmethod
    def _phone_slot_for(kingschat_user_id: str) -> str:
        return f"{KINGSCHAT_ID_PREFIX}{kingschat_user_id}"

    async def get_or_create_user(self, kingschat_user_id: str) -> User:
        phone_slot = self._phone_slot_for(kingschat_user_id)
        result = await self.db.execute(select(User).where(User.phone_number == phone_slot))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                phone_number=phone_slot,
                name="KingsChat User",
                language=Language.ENGLISH,
                current_day=1,
                preferred_channel="kingschat",
                consent_given=True,
                data_retention_date=datetime.utcnow(),
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

        return user

    async def get_or_create_conversation(self, user_id: int, kingschat_user_id: str) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.channel == ConversationChannel.KINGSCHAT,
                Conversation.is_active == True,
            )
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            conversation = Conversation(
                user_id=user_id,
                channel=ConversationChannel.KINGSCHAT,
                phone_number=self._phone_slot_for(kingschat_user_id),
                external_id=kingschat_user_id,
                current_state=ConversationState.NEW_USER,
                is_active=True,
            )
            self.db.add(conversation)
            await self.db.commit()
            await self.db.refresh(conversation)

        return conversation

    async def handle_message(self, session: "KingsChatSession", kingschat_user_id: str, message_text: str) -> None:
        user = await self.get_or_create_user(kingschat_user_id)
        user.last_active_at = datetime.utcnow()
        await self.db.commit()

        conversation = await self.get_or_create_conversation(user.id, kingschat_user_id)

        if message_text.strip().upper() == "CONTINUE" and conversation.current_state in (
            ConversationState.IN_LESSON,
            ConversationState.AWAITING_QUIZ,
            ConversationState.DAY_COMPLETE,
        ):
            await self.handle_continue(session, kingschat_user_id, user, conversation)
            return

        # Global command: claim/regenerate a certificate — reachable from any
        # state, mirroring the same fix in whatsapp.py's handle_message.
        # Catches a returning learner whose prior conversation is stale
        # (still NEW_USER, IN_LESSON, etc.) just as much as one sitting in
        # DAY_COMPLETE from the natural completion flow.
        if message_text.strip().upper() == "CERTIFICATE" and conversation.current_state not in (
            ConversationState.AWAITING_QUIZ,
            ConversationState.AWAITING_LANGUAGE,
            ConversationState.AWAITING_CERTIFICATE_NAME,
        ):
            await self.handle_certificate_request(session, kingschat_user_id, user, conversation)
            return

        if conversation.current_state == ConversationState.NEW_USER:
            await self.handle_new_user(session, kingschat_user_id, user, conversation)
        elif conversation.current_state == ConversationState.AWAITING_LANGUAGE:
            await self.handle_language_selection(session, kingschat_user_id, user, conversation, message_text)
        elif conversation.current_state == ConversationState.IN_LESSON:
            await self.handle_lesson_flow(session, kingschat_user_id, user, conversation, message_text)
        elif conversation.current_state == ConversationState.AWAITING_QUIZ:
            await self.handle_quiz_response(session, kingschat_user_id, user, conversation, message_text)
        elif conversation.current_state == ConversationState.DAY_COMPLETE:
            await self.handle_day_complete(session, kingschat_user_id, user, conversation, message_text)
        elif conversation.current_state == ConversationState.AWAITING_CERTIFICATE_NAME:
            await self.handle_certificate_name(session, kingschat_user_id, user, conversation, message_text)
        else:
            await self.handle_new_user(session, kingschat_user_id, user, conversation)

    async def handle_new_user(self, session, kingschat_user_id, user: User, conversation: Conversation) -> None:
        await session.send_message(kingschat_user_id, self.message_builder.build_welcome_message())
        conversation.current_state = ConversationState.AWAITING_LANGUAGE
        await self.db.commit()

    async def handle_language_selection(self, session, kingschat_user_id, user: User, conversation: Conversation, selection: str) -> None:
        language_map = {
            "1": Language.ENGLISH, "2": Language.PIDGIN, "3": Language.HAUSA,
            "4": Language.YORUBA, "5": Language.IGBO,
        }
        selected = language_map.get(selection.strip())
        if not selected:
            await session.send_message(
                kingschat_user_id,
                "Please reply with a number 1-5 to choose your language.",
            )
            return

        user.language = selected
        conversation.current_state = ConversationState.IN_LESSON
        conversation.context = {}
        await self.db.commit()
        await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)

    async def handle_continue(self, session, kingschat_user_id, user: User, conversation: Conversation) -> None:
        if conversation.current_state == ConversationState.AWAITING_QUIZ:
            lesson_id = conversation.context.get("current_lesson_id")
            current_question = conversation.context.get("current_question", 0)
            if lesson_id:
                result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
                lesson = result.scalar_one_or_none()
                if lesson and current_question < len(lesson.quiz):
                    num_options = len(lesson.quiz[current_question]["options"])
                    order, new_context = get_or_create_shuffle(conversation.context, current_question, num_options)
                    if new_context is not conversation.context:
                        conversation.context = new_context
                        await self.db.commit()
                    await session.send_message(
                        kingschat_user_id,
                        self.message_builder.build_quiz_message(lesson, current_question, order),
                    )
                    return
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)
        elif conversation.current_state == ConversationState.DAY_COMPLETE:
            if user.current_day < 7:
                await self.handle_day_complete(session, kingschat_user_id, user, conversation, "NEXT")
            else:
                await self.handle_certificate_request(session, kingschat_user_id, user, conversation)
        else:
            await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)

    async def deliver_next_lesson(self, session, kingschat_user_id, user: User, conversation: Conversation) -> None:
        next_lesson = await self.lesson_manager.get_next_lesson(user.id, user.language.value)

        if not next_lesson:
            await self.handle_day_completion(session, kingschat_user_id, user, conversation)
            return

        topic_order = self.lesson_manager.TOPIC_ORDER
        result = await self.db.execute(
            select(Lesson).where(Lesson.day == user.current_day, Lesson.language == user.language.value)
        )
        day_lessons = sorted(
            result.scalars().all(),
            key=lambda l: topic_order.index(l.topic) if l.topic in topic_order else 99,
        )
        lesson_number = day_lessons.index(next_lesson) + 1

        await session.send_message(
            kingschat_user_id,
            self.message_builder.build_lesson_message(next_lesson, lesson_number),
        )

        conversation.context = {"current_lesson_id": next_lesson.id}
        conversation.current_state = ConversationState.IN_LESSON
        await self.db.commit()

    async def handle_lesson_flow(self, session, kingschat_user_id, user: User, conversation: Conversation, message_text: str) -> None:
        if message_text.strip().upper() in ("QUIZ", "RETRY"):
            lesson_id = conversation.context.get("current_lesson_id")
            if not lesson_id:
                await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)
                return

            result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
            lesson = result.scalar_one_or_none()

            if lesson:
                order, shuffled_context = get_or_create_shuffle({}, 0, len(lesson.quiz[0]["options"]))
                await session.send_message(
                    kingschat_user_id,
                    self.message_builder.build_quiz_message(lesson, 0, order),
                )
                conversation.current_state = ConversationState.AWAITING_QUIZ
                conversation.context = {
                    **shuffled_context,
                    "current_lesson_id": lesson_id,
                    "current_question": 0,
                    "answers": [],
                }
                await self.db.commit()
        else:
            await session.send_message(
                kingschat_user_id,
                "Reply QUIZ when you're ready to test your knowledge! 📝",
            )

    async def handle_quiz_response(self, session, kingschat_user_id, user: User, conversation: Conversation, response: str) -> None:
        """Same context-threading contract as
        whatsapp.py:WhatsAppWebhookHandler.handle_quiz_response — this is
        deliberately parallel structure, not copy-paste laziness: the bug
        fixed there (a freshly-created shuffle silently discarded in the
        defensive fallback path) is the exact class of bug the eng review's
        test plan flagged as a regression risk for this file too. See
        backend/tests/test_kingschat_flow.py::test_quiz_shuffle_context_not_discarded.
        """
        lesson_id = conversation.context.get("current_lesson_id")
        current_question = conversation.context.get("current_question", 0)

        if not lesson_id:
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)
            return

        letter = response.strip().upper()[:1]
        display_position = ord(letter) - ord("A") if letter in ("A", "B", "C", "D") else None

        result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
        lesson = result.scalar_one_or_none()

        if display_position is None or not lesson or current_question >= len(lesson.quiz):
            if lesson and current_question < len(lesson.quiz):
                order, new_context = get_or_create_shuffle(
                    conversation.context, current_question, len(lesson.quiz[current_question]["options"])
                )
                if new_context is not conversation.context:
                    conversation.context = new_context
                    await self.db.commit()
                await session.send_message(
                    kingschat_user_id,
                    self.message_builder.build_quiz_message(lesson, current_question, order),
                )
            return

        num_options = len(lesson.quiz[current_question]["options"])
        if display_position >= num_options:
            order, new_context = get_or_create_shuffle(conversation.context, current_question, num_options)
            if new_context is not conversation.context:
                conversation.context = new_context
                await self.db.commit()
            await session.send_message(
                kingschat_user_id,
                self.message_builder.build_quiz_message(lesson, current_question, order),
            )
            return

        # Thread context through both lookups rather than discarding either
        # — see the docstring above and the WhatsApp fix this mirrors.
        current_order, working_context = get_or_create_shuffle(conversation.context, current_question, num_options)
        answer_idx = unshuffle_answer(display_position, current_order)

        answers = working_context.get("answers", [])
        answers.append(answer_idx)

        if current_question < 4:
            next_question = current_question + 1
            next_order, shuffled_context = get_or_create_shuffle(
                working_context, next_question, len(lesson.quiz[next_question]["options"])
            )
            conversation.context = {**shuffled_context, "current_question": next_question, "answers": answers}
            await self.db.commit()
            await session.send_message(
                kingschat_user_id,
                self.message_builder.build_quiz_message(lesson, next_question, next_order),
            )
        else:
            quiz_result = await self.lesson_manager.record_quiz_attempt(user.id, lesson_id, answers)
            await session.send_message(
                kingschat_user_id,
                self.message_builder.build_quiz_result_message(
                    quiz_result.score, quiz_result.passed, quiz_result.attempt_number, quiz_result.can_retry
                ),
            )

            if quiz_result.passed:
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {}
                await self.db.commit()
                await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)
            else:
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {"current_lesson_id": lesson_id}
                await self.db.commit()

    RESERVED_NAME_WORDS = {"next", "quiz", "continue", "certificate", "retry", "yes", "no"}

    async def handle_day_completion(self, session, kingschat_user_id, user: User, conversation: Conversation) -> None:
        await self.lesson_manager.mark_day_complete(user.id, user.current_day)
        progress = await self.lesson_manager.get_user_progress(user.id)
        needs_name = user.current_day == 7 and not user.name_confirmed

        await session.send_message(
            kingschat_user_id,
            self.message_builder.build_day_complete_message(
                user.current_day, progress.current_day_progress, needs_name=needs_name
            ),
        )

        conversation.current_state = (
            ConversationState.AWAITING_CERTIFICATE_NAME if needs_name else ConversationState.DAY_COMPLETE
        )
        await self.db.commit()

    async def handle_certificate_name(self, session, kingschat_user_id, user: User, conversation: Conversation, message_text: str) -> None:
        candidate = message_text.strip()

        if len(candidate) < 2 or len(candidate) > 255 or candidate.lower() in self.RESERVED_NAME_WORDS:
            await session.send_message(
                kingschat_user_id,
                "Please reply with the full name you'd like printed on your certificate.",
            )
            return

        user.name = candidate
        user.name_confirmed = True
        await self.db.commit()

        await session.send_message(
            kingschat_user_id,
            f"Got it — your certificate will say {candidate}. Generating it now...",
        )

        await self.generate_and_send_certificate(session, kingschat_user_id, user, conversation)

    async def handle_certificate_request(self, session, kingschat_user_id: str, user: User, conversation: Conversation) -> None:
        """
        Entry point for the CERTIFICATE command, reachable from any state —
        mirrors whatsapp.py's handle_certificate_request. Covers both the
        natural Day 7 completion flow and a learner texting CERTIFICATE cold
        from a stale/reset conversation.
        """
        if user.completed_days < 7:
            await session.send_message(
                kingschat_user_id,
                f"You're on Day {user.current_day}/7 — finish all 7 days to unlock your certificate! 💪",
            )
            return

        if not user.name_confirmed:
            conversation.current_state = ConversationState.AWAITING_CERTIFICATE_NAME
            await self.db.commit()
            await session.send_message(
                kingschat_user_id,
                "🎓 You're eligible for your certificate! What name should appear on it? Reply with your full name.",
            )
            return

        await self.generate_and_send_certificate(session, kingschat_user_id, user, conversation)

    async def generate_and_send_certificate(self, session, kingschat_user_id: str, user: User, conversation: Conversation) -> None:
        """
        Generate (or fetch the already-issued) certificate and send the
        download link right away. generate_and_store_certificate is
        idempotent — a repeat call just returns the certificate already on
        file instead of making a new one.
        """
        from app.certificates.generator import CertificateGenerator
        from urllib.parse import quote

        generator = CertificateGenerator(self.db, self.settings)

        try:
            certificate = await generator.generate_and_store_certificate(
                user_id=user.id, language=user.language.value
            )
        except Exception:
            logger.exception("kingschat_certificate_generation_failed user_id=%s", user.id)
            await session.send_message(
                kingschat_user_id,
                "⚠️ We couldn't generate your certificate right now. Please reply CERTIFICATE to try again in a few minutes.",
            )
            return

        conversation.current_state = ConversationState.PROGRAM_COMPLETE
        await self.db.commit()

        verify_url = (
            f"{self.settings.FRONTEND_URL}/verify"
            f"?code={certificate.certificate_id}&name={quote(user.name)}"
        )
        await session.send_message(
            kingschat_user_id,
            f"🎓 Congratulations, {user.name}! Your MNAIR certificate is ready.\n\n"
            f"Code: {certificate.certificate_id}\n"
            f"Download: {verify_url}",
        )

    async def handle_day_complete(self, session, kingschat_user_id, user: User, conversation: Conversation, message_text: str) -> None:
        cmd = message_text.strip().upper()

        if cmd == "NEXT":
            advanced = await self.lesson_manager.advance_to_next_day(user.id)
            if advanced:
                await self.db.refresh(user)
                conversation.current_state = ConversationState.IN_LESSON
                await self.db.commit()
                await self.deliver_next_lesson(session, kingschat_user_id, user, conversation)
            else:
                await session.send_message(
                    kingschat_user_id,
                    "❌ Couldn't advance to next day. Please ensure all lessons are complete.",
                )
        else:
            next_action = "Reply NEXT to continue!" if user.current_day < 7 else "Reply CERTIFICATE to claim your certificate!"
            await session.send_message(
                kingschat_user_id,
                f"🎊 You've completed Day {user.current_day}!\n\n{next_action}",
            )


class KingsChatLoginError(Exception):
    """Raised when an interactive login attempt fails — wrong credentials,
    or a challenge (CAPTCHA/2FA) this adapter can't solve. Distinct from
    KingsChatBanDetectedError, which is for a session that WAS valid and
    stopped being valid; this is for a session that never got established
    in the first place.
    """


async def _goto_and_settle(page, url: str, *, timeout_ms: int = 5000) -> None:
    """Navigate and give the SPA a bounded window to settle, without
    trusting `wait_for_load_state("networkidle")` to ever actually
    resolve.

    Confirmed live 2026-07-12: kingschat.online is a real-time chat app
    with what's almost certainly a persistent WebSocket connection for
    live messages, so "networkidle" (no network activity for 500ms) can
    hang for the FULL default 30s timeout and crash the caller -- this
    happened mid-testing on `ensure_logged_in`'s validity check. Bounding
    the wait and swallowing the timeout keeps the "give the page a moment
    to render" benefit for the common case (most navigations finish well
    under this window even with background socket chatter) without ever
    blocking the caller for 30s or raising on a page that's actually fine,
    just never fully "idle" by this app's nature.

    Also confirmed live 2026-07-12: `goto()`'s own default wait_until
    ("load" -- every resource on the page finished loading) can ALSO
    time out at 30s on this app, a second symptom of the same
    never-fully-quiet root cause. `wait_until="domcontentloaded"` here
    resolves as soon as the HTML is parsed, not once every subresource
    (images, the WebSocket connection, background polling) has settled --
    standard practice for automating a modern SPA, not a workaround
    specific to a bug.

    Confirmed live 2026-07-17, during the first real --live run: even
    `domcontentloaded` can time out on this app -- caught mid-run navigating
    to /conversations with a stored session applied, then confirmed by
    inspecting page.url and page.inner_text("body") immediately after the
    exception that the real inbox UI ("Chats", "Timeline", "New" etc.) had
    already fully rendered. The navigation had actually succeeded; only
    Playwright's own bookkeeping for "this event fired" hadn't caught up
    within the window, almost certainly the same persistent-WebSocket cause
    documented above showing up one layer earlier. A goto() timeout on this
    app is therefore not proof the navigation failed, exactly like
    _settle's networkidle wait below -- swallowed here for the same reason,
    with a longer bound than _settle's since goto() has more work to do
    than a post-load quiet check.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms * 3)
    except Exception:
        pass
    await _settle(page, timeout_ms=timeout_ms)


async def _settle(page, *, timeout_ms: int = 5000) -> None:
    """Bounded wait for network quiet after an in-page action (click, etc)
    that doesn't go through goto — same rationale as _goto_and_settle."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


async def kingschat_login(page, email: str, password: str) -> dict:
    """Perform an interactive login and return the resulting storage_state
    (cookies + localStorage) for KingsChatSessionStore to persist.

    Selectors verified live 2026-07-12 (see module docstring) — this is
    the exact sequence used during that verification, now automated:
    fill #usernameOrEmail, fill #password, click the submit button, then
    check for the password-error banner to distinguish success from a
    rejected login rather than assuming success from a lack of exception.
    """
    await _goto_and_settle(page, "https://accounts.kingschat.online/log-in")

    await page.locator(SELECTORS.login_username_input).fill(email)
    await page.locator(SELECTORS.login_password_input).fill(password)
    await page.locator(SELECTORS.login_submit_button).click()

    # `networkidle` alone isn't enough here: the Log In button shows an
    # in-flight spinner while its auth request/reCAPTCHA-token round trip
    # is still pending, and networkidle can resolve before that finishes
    # (confirmed live 2026-07-12 -- a screenshot taken right after
    # networkidle caught the button still spinning, with the URL not yet
    # changed and no error banner, i.e. neither terminal state). Poll for
    # an actual terminal state instead of trusting a single point-in-time
    # check: either the URL leaves the login domain (success) or the
    # error banner appears (rejected).
    #
    # Also confirmed live: polling DURING the moment navigation actually
    # happens can throw "Execution context was destroyed" from the
    # in-flight locator query racing the page transition -- tolerate that
    # specific transient error rather than letting it crash the login
    # attempt outright; it means navigation is actively happening, which
    # is progress, not a failure.
    for _ in range(30):  # ~15s at 0.5s/poll -- login is slow, don't rush it
        if "accounts.kingschat.online" not in page.url:
            break
        try:
            if await page.locator(SELECTORS.login_error_banner).count() > 0:
                break
        except Exception as e:
            if "Execution context was destroyed" not in str(e):
                raise
        await page.wait_for_timeout(500)

    # Let a navigation that was in-flight when the loop above exited
    # actually settle before the final, authoritative check below --
    # otherwise that check inherits the same race.
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    if await page.locator(SELECTORS.login_error_banner).count() > 0:
        raise KingsChatLoginError(
            "KingsChat rejected the configured KINGSCHAT_ACCOUNT_EMAIL/"
            "KINGSCHAT_ACCOUNT_PASSWORD — verified live against the "
            "real login form on 2026-07-12, so this is a credentials "
            "problem, not a selector problem."
        )

    # Still on the login domain after submit with no error banner is an
    # unexpected third state (e.g. a challenge this adapter doesn't
    # recognize) -- don't silently treat it as success. Capture a
    # screenshot + text dump here rather than raising blind: this is
    # exactly the failure mode that shouldn't need a second live login
    # attempt against a real account just to see what's actually blocking.
    if "accounts.kingschat.online" in page.url:
        diag_dir = Path.home() / "kingschat_login_diagnostics"
        diag_dir.mkdir(exist_ok=True)
        screenshot_path = diag_dir / "last_failure.png"
        text_path = diag_dir / "last_failure.txt"
        try:
            await page.screenshot(path=str(screenshot_path))
            text_path.write_text(await page.inner_text("body"), encoding="utf-8")
        except Exception:
            logger.exception("kingschat_login_diagnostic_capture_failed")
        raise KingsChatLoginError(
            f"Login submitted with no error banner but still on the "
            f"login domain ({page.url}) -- possibly a CAPTCHA or 2FA "
            f"challenge this adapter doesn't handle. Diagnostics saved to "
            f"{screenshot_path} and {text_path}."
        )

    return await page.context.storage_state()


class SelectorDriftError(Exception):
    """Raised when a selector that should exist doesn't — signals a
    KingsChat frontend deploy has changed the DOM out from under this
    adapter, per this file's module-docstring note on UI-drift as its own
    failure mode distinct from account bans. Caught the same way a ban is
    caught: triggers KingsChatBanFallback so it degrades to the manual
    fallback rather than failing silently."""


class KingsChatSession:
    """Wraps a single acquired BrowserContext page for one send/receive
    operation. See KingsChatBrowserPool for how contexts are acquired —
    this class only knows how to talk to a single already-authenticated
    page, not how to log in or manage the pool.
    """

    def __init__(self, page):
        self._page = page

    async def send_message(self, kingschat_user_id: str, text: str) -> None:
        """Navigate to the learner's conversation and send `text`.

        kingschat_user_id is actually the KingsChat conversation ID (see
        this module's docstring) — navigation is a direct URL, there's no
        separate thread-lookup step.

        Uses the confirmed click-based Send button, not Enter-to-submit —
        Enter's behavior in this Tiptap/ProseMirror editor (send vs.
        newline) was deliberately NOT tested against a real conversation
        during selector verification (see module docstring). Multi-line
        lesson text (this app sends lessons with embedded '\\n's) should
        get a dedicated test against a disposable conversation before this
        handles production traffic — if Enter turns out to submit early,
        typing a multi-line message would send it in fragments.

        Confirmed live 2026-07-17 during the first real send test: this
        conversation's composer did NOT reliably render within
        _goto_and_settle's window on every attempt -- one call found it
        immediately, a follow-up call moments later on the SAME
        conversation raised SelectorDriftError from a bare .count()==0
        check. That's a timing race, not proof of real drift (the earlier
        successful send is direct evidence the selector itself is still
        correct) -- the composer check below now waits (bounded) for the
        element to actually appear, the same pattern the Send button check
        just after it already used correctly. A genuine drift (composer
        never appears within the wait) still raises SelectorDriftError.
        """
        await _goto_and_settle(self._page, f"https://kingschat.online/conversations/{kingschat_user_id}")

        if await self._page.locator(SELECTORS.logged_out_redirect_marker).count() > 0:
            raise KingsChatBanDetectedError(
                f"Redirected to login while navigating to conversation "
                f"{kingschat_user_id} — session expired or was invalidated."
            )

        editor = self._page.locator(SELECTORS.message_input)
        try:
            await editor.first.wait_for(state="visible", timeout=15000)
        except Exception as e:
            raise SelectorDriftError(
                f"Message composer ({SELECTORS.message_input}) not found "
                f"on conversation {kingschat_user_id} — KingsChat's DOM "
                f"may have changed since selectors were last verified."
            ) from e

        await editor.first.click()
        # Confirmed live 2026-07-17: Playwright's type() default 30s timeout
        # is not always enough for real lesson content (curriculum lessons
        # run up to ~1900 chars -- see whatsapp.py's build_lesson_message
        # comment) typed keystroke-by-keystroke into a Tiptap/ProseMirror
        # editor, where every character can trigger a full editor
        # transaction + re-render. A short "START"-length reply worked fine
        # at the default; the actual Day 1 lesson timed out. Scale the
        # timeout to content length instead of guessing a single fixed
        # value -- generous floor for short replies, headroom for the
        # longest real lesson.
        await editor.first.type(text, timeout=max(30000, len(text) * 50))

        send = self._page.locator(SELECTORS.send_button)
        try:
            await send.wait_for(state="visible", timeout=5000)
        except Exception as e:
            raise SelectorDriftError(
                f"Send button ({SELECTORS.send_button}) never appeared "
                f"after typing into conversation {kingschat_user_id} — "
                f"expected it to appear once the composer has content."
            ) from e
        await send.click()

    async def detect_ban(self) -> bool:
        """Check the current page for suspension/CAPTCHA/logged-out signals.
        Returns True if a ban/suspension is detected.

        Unlike send_message's SelectorDriftError distinction, this method
        intentionally treats "selector not found" as "signal not present"
        (the normal, expected case) rather than an error — these selectors
        were never verified against a real ban event (see module
        docstring), so a false negative here is the honest failure mode to
        design for, not a false SelectorDriftError on every healthy check.
        """
        for selector in (
            SELECTORS.account_suspended_banner,
            SELECTORS.captcha_challenge,
        ):
            if await self._page.locator(selector).count() > 0:
                return True
        return False

    async def list_unread_direct_conversation_ids(self, contact_filter: Optional[str] = None) -> list[str]:
        """Navigate to the inbox, filter to Direct (1:1) only — Groups are
        explicitly out of scope (Open Question 5) — and return the
        conversation IDs of unread threads by clicking each one and
        reading the resulting URL, since KingsChat's conversation list
        items carry no ID in their own DOM attributes (see module
        docstring): the ID only appears in the URL after navigating in.

        Clicking marks a conversation read, so this is destructive with
        respect to unread state -- call it once per poll cycle, not
        speculatively.

        contact_filter: if given, only clicks into (and thus only marks
        read / returns) unread rows whose visible text contains this
        substring (case-insensitive) -- e.g. a display name or handle.
        Every non-matching unread row is inspected read-only (inner_text
        only, never clicked) and left exactly as it was. This exists for
        safely scoping a manual test run (see kingschat_bot.py's
        --only-contact) to one known conversation without touching
        whatever else happens to be unread in a real, actively-used inbox
        -- production polling (no filter) still processes everything.
        """
        await _goto_and_settle(self._page, "https://kingschat.online/conversations")

        direct_tab = self._page.locator("text=Direct")
        if await direct_tab.count() > 0:
            await direct_tab.first.click()
            await _settle(self._page)

        conversation_ids: list[str] = []
        # Re-query after each click rather than iterating a stale locator
        # list -- clicking navigates away and the inbox list panel
        # persists, but the returned collection would otherwise reference
        # elements from before that navigation.
        while True:
            target = await self._find_next_unread_row(contact_filter)
            if target is None:
                break
            await target.click()
            await _settle(self._page)
            conversation_id = self._page.url.rstrip("/").rsplit("/", 1)[-1]
            conversation_ids.append(conversation_id)
            await _goto_and_settle(self._page, "https://kingschat.online/conversations")
            direct_tab = self._page.locator("text=Direct")
            if await direct_tab.count() > 0:
                await direct_tab.first.click()
                await _settle(self._page)

        return conversation_ids

    async def _find_next_unread_row(self, contact_filter: Optional[str]):
        """Return a Locator for the next unread conversation row to act on,
        or None if there isn't one (matching the filter, if given).

        No filter: behaves exactly as the old implementation (first unread
        row in DOM order). With a filter: scans full conversation rows
        (not just the unread badge) for one that is BOTH unread AND has the
        filter substring anywhere in its rendered text, read-only for every
        row that doesn't match -- never clicks a non-matching row.
        """
        if contact_filter is None:
            unread = self._page.locator(SELECTORS.unread_direct_item)
            return unread.first if await unread.count() > 0 else None

        rows = self._page.locator(SELECTORS.direct_conversation_item)
        for i in range(await rows.count()):
            row = rows.nth(i)
            if await row.locator(SELECTORS.unread_direct_item).count() == 0:
                continue
            text = (await row.inner_text()).strip()
            if contact_filter.lower() in text.lower():
                return row
        return None

    async def read_latest_incoming_message(self) -> Optional[str]:
        """Read the text of the most recent message NOT sent by this
        account, on whatever conversation the page is currently on. Must
        be called after navigating to a specific conversation (e.g. via
        list_unread_direct_conversation_ids, which leaves the page on the
        conversation it just opened).
        """
        bubbles = self._page.locator(SELECTORS.message_bubble)
        count = await bubbles.count()
        for i in range(count - 1, -1, -1):
            bubble = bubbles.nth(i)
            class_attr = await bubble.get_attribute("class") or ""
            if SELECTORS.message_bubble_outgoing_modifier in class_attr:
                continue
            text_el = bubble.locator(SELECTORS.message_text)
            if await text_el.count() == 0:
                continue
            return (await text_el.first.text_content() or "").strip()
        return None


class DryRunKingsChatSession:
    """Wraps a real KingsChatSession for safe first-time testing — every
    read (list_unread_direct_conversation_ids, read_latest_incoming_message,
    detect_ban) hits the real page exactly like the live session, but
    send_message logs what WOULD be sent instead of clicking Send.

    This is the default in kingschat_bot.py deliberately: the first run
    against a real account should not be able to post into a real
    conversation by accident. Use --live to get the real KingsChatSession.
    """

    def __init__(self, real_session: KingsChatSession):
        self._real = real_session
        self.sent_log: list[tuple[str, str]] = []

    async def send_message(self, kingschat_user_id: str, text: str) -> None:
        logger.info(
            "kingschat_dry_run_send conversation=%s text=%r", kingschat_user_id, text
        )
        self.sent_log.append((kingschat_user_id, text))

    async def detect_ban(self) -> bool:
        return await self._real.detect_ban()

    async def list_unread_direct_conversation_ids(self, contact_filter: Optional[str] = None) -> list[str]:
        return await self._real.list_unread_direct_conversation_ids(contact_filter)

    async def read_latest_incoming_message(self) -> Optional[str]:
        return await self._real.read_latest_incoming_message()


class KingsChatWatcher:
    """Ties the pieces together: poll the inbox for unread DMs, read the
    latest incoming message, dispatch it through KingsChatHandler (the
    same state machine whatsapp.py/ussd.py use, per Premise 2), and send
    the computed reply back. This is the piece that turns the individual
    components (session store, browser pool, handler, message builder)
    into something that actually runs — see kingschat_bot.py for the
    runnable entrypoint that constructs one of these.
    """

    def __init__(self, handler: KingsChatHandler, ban_fallback: KingsChatBanFallback):
        self.handler = handler
        self.ban_fallback = ban_fallback

    async def poll_once(self, session, contact_filter: Optional[str] = None) -> int:
        """One poll cycle: check for a ban first, then process every
        currently-unread Direct conversation. Returns the number of
        messages processed. `session` accepts either a real
        KingsChatSession or a DryRunKingsChatSession -- both expose the
        same interface.

        contact_filter: scope this cycle to only unread conversations whose
        visible text matches this substring (see KingsChatSession's
        _find_next_unread_row) -- everything else unread is left completely
        untouched. Used by kingschat_bot.py's --only-contact for safely
        testing against one known conversation on a real, actively-used
        inbox. None (default) processes everything, as before.
        """
        if await session.detect_ban():
            await self.ban_fallback.notify_leader(lesson=None, reason="ban/suspension signal detected during poll")
            raise KingsChatBanDetectedError("Ban signal detected at start of poll cycle")

        conversation_ids = await session.list_unread_direct_conversation_ids(contact_filter)
        processed = 0
        for conversation_id in conversation_ids:
            message_text = await session.read_latest_incoming_message()
            if message_text is None:
                logger.warning(
                    "kingschat_no_incoming_message_found conversation=%s -- "
                    "unread marker present but no non-outgoing message found",
                    conversation_id,
                )
                continue
            await self.handler.handle_message(session, conversation_id, message_text)
            processed += 1

        return processed
