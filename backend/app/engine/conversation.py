"""
ConversationEngine — the 7-day learning flow, independent of any channel.

Ported from the retired WhatsApp webhook handler with one structural change:
the engine never sends anything. `handle()` returns the list of
OutboundMessage objects the channel should deliver, in order, after the
database work has been committed. That is what lets the same code serve a
Telegram bot (push each message via the Bot API) and the web learner app
(return them in the HTTP response) with no per-message cost on either.

State machine (unchanged):
    NEW_USER -> AWAITING_LANGUAGE -> IN_LESSON <-> AWAITING_QUIZ
             -> DAY_COMPLETE -> (AWAITING_CERTIFICATE_NAME) -> PROGRAM_COMPLETE

Global commands reachable from (almost) any state: LANGUAGE, CONTINUE,
CERTIFICATE, CODE <sponsor code>, PAY. Button ids map onto the same keywords, so a tap and a typed
reply are indistinguishable to the engine.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.engine.builder import MessageBuilder, LANGUAGE_NAMES
from app.engine.messages import OutboundMessage
from app.models.conversation import Conversation, ConversationState
from app.models.lesson import Lesson
from app.models.user import User, Language
from app.services.lesson_state import LessonStateManager
from app.services.quiz_shuffle import get_or_create_shuffle, unshuffle_answer

logger = logging.getLogger(__name__)


# Button ids that are plain keyword aliases. A tap on "next" is handled
# exactly like a typed "NEXT".
COMMAND_BUTTON_IDS = {
    "quiz": "QUIZ",
    "retry": "RETRY",
    "next": "NEXT",
    "certificate": "CERTIFICATE",
    "continue_learning": "CONTINUE",
    "language": "LANGUAGE",
    "yes": "YES",
    "no": "NO",
    "start": "START",
    "pay_certificate": "PAY",
}

LANGUAGE_MAP = {
    "lang_en": Language.ENGLISH,
    "lang_pid": Language.PIDGIN,
    "lang_ha": Language.HAUSA,
    "lang_yo": Language.YORUBA,
    "lang_ig": Language.IGBO,
}

# Typed language names accepted in place of a button tap.
LANGUAGE_WORDS = {
    "ENGLISH": "lang_en", "EN": "lang_en", "1": "lang_en",
    "PIDGIN": "lang_pid", "NAIJA": "lang_pid", "PID": "lang_pid", "2": "lang_pid",
    "HAUSA": "lang_ha", "HA": "lang_ha", "3": "lang_ha",
    "YORUBA": "lang_yo", "YO": "lang_yo", "4": "lang_yo",
    "IGBO": "lang_ig", "IG": "lang_ig", "5": "lang_ig",
}

# Reserved commands a name reply must not collide with, so someone who
# taps a stale button or types a command while being asked for their
# name doesn't get that word stored as their certificate name
RESERVED_NAME_WORDS = {"next", "quiz", "continue", "certificate", "language", "retry", "yes", "no", "start", "pay"}

HISTORY_LIMIT = 40


class ConversationEngine:
    """Drives one learner turn: (user, conversation, input) -> outbound messages."""

    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings
        self.builder = MessageBuilder()
        self.lesson_manager = LessonStateManager(db)
        self._outbox: List[OutboundMessage] = []

    # ------------------------------------------------------------------
    # Outbox / history helpers
    # ------------------------------------------------------------------

    def _emit(self, conversation: Conversation, message: OutboundMessage) -> None:
        self._outbox.append(message)
        self._record(conversation, "bot", message)

    @staticmethod
    def _record(conversation: Conversation, role: str, message) -> None:
        """Append to message_history, reassigning the list so SQLAlchemy
        detects the JSON change (in-place mutation is invisible to it)."""
        history = list(conversation.message_history or [])
        entry = {"role": role, "timestamp": datetime.utcnow().isoformat()}
        if isinstance(message, OutboundMessage):
            entry.update(message.to_dict())
        else:
            entry["text"] = str(message)
            entry["kind"] = "text"
            entry["buttons"] = []
        history.append(entry)
        conversation.message_history = history[-HISTORY_LIMIT:]
        conversation.last_message_at = datetime.utcnow()

    async def _get_lesson(self, lesson_id: int) -> Optional[Lesson]:
        result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def handle(
        self,
        user: User,
        conversation: Conversation,
        message_text: str = "",
        interactive_id: Optional[str] = None,
    ) -> List[OutboundMessage]:
        """Process one inbound event and return the replies to deliver."""
        self._outbox = []
        message_text = (message_text or "").strip()

        # Buttons that are keyword aliases become the keyword itself.
        if interactive_id in COMMAND_BUTTON_IDS:
            message_text = COMMAND_BUTTON_IDS[interactive_id]
            interactive_id = None

        # Typed language names work like the language buttons.
        if (
            conversation.current_state == ConversationState.AWAITING_LANGUAGE
            and not interactive_id
            and message_text.upper() in LANGUAGE_WORDS
        ):
            interactive_id = LANGUAGE_WORDS[message_text.upper()]

        # Typed answer letters/numbers work like the answer buttons.
        if (
            conversation.current_state == ConversationState.AWAITING_QUIZ
            and not interactive_id
            and message_text
        ):
            interactive_id = self._typed_answer_to_button(conversation, message_text)

        self._record(conversation, "user", interactive_id or message_text)

        # Track activity — drives reminder eligibility
        user.last_active_at = datetime.utcnow()
        await self.db.commit()

        upper = message_text.upper()

        # Global command: redeem a sponsor code ("CODE GRACE-7K2Q"). A brand
        # new learner (Telegram deep link t.me/<bot>?start=<CODE>) still gets
        # onboarded straight after.
        if upper.startswith("CODE ") and conversation.current_state != ConversationState.AWAITING_CERTIFICATE_NAME:
            await self.handle_sponsor_code(user, conversation, message_text[5:])
            if conversation.current_state == ConversationState.NEW_USER:
                await self.handle_new_user(user, conversation)
            await self.db.commit()
            return self._outbox

        if upper == "CODE":
            self._emit(conversation, OutboundMessage.text_only(
                "Reply *CODE* followed by your sponsor code, for example: CODE GRACE-7K2Q"
            ))
            await self.db.commit()
            return self._outbox

        # Global command: pay for a verified certificate
        if upper == "PAY" and conversation.current_state != ConversationState.AWAITING_CERTIFICATE_NAME:
            await self.handle_certificate_request(user, conversation)
            return self._outbox

        # Global command: change language from anywhere
        if upper == "LANGUAGE":
            conversation.context = {
                **(conversation.context or {}),
                "pending_language_change": True,
                "saved_context": conversation.context or {},  # preserve lesson position for NO cancellation
            }
            conversation.previous_state = conversation.current_state
            conversation.current_state = ConversationState.AWAITING_LANGUAGE
            self._emit(conversation, self.builder.build_language_selector())
            await self.db.commit()
            return self._outbox

        # YES/NO confirmation for a mid-course language change
        if upper in ("YES", "NO") and (conversation.context or {}).get("confirming_language_change"):
            await self.handle_language_change_confirmation(user, conversation, upper)
            return self._outbox

        # Global command: resume learning (typed CONTINUE or reminder button tap)
        if upper == "CONTINUE" and conversation.current_state in (
            ConversationState.IN_LESSON,
            ConversationState.AWAITING_QUIZ,
            ConversationState.DAY_COMPLETE,
        ):
            await self.handle_continue(user, conversation)
            return self._outbox

        # Global command: claim/regenerate a certificate — reachable from any
        # state, including a brand-new conversation for a returning learner
        # whose previous session already ended.
        if upper == "CERTIFICATE" and conversation.current_state not in (
            ConversationState.AWAITING_QUIZ,
            ConversationState.AWAITING_LANGUAGE,
            ConversationState.AWAITING_CERTIFICATE_NAME,
        ):
            await self.handle_certificate_request(user, conversation)
            return self._outbox

        # Global command: progress summary
        if upper in ("PROGRESS", "STATUS") and conversation.current_state not in (
            ConversationState.NEW_USER,
            ConversationState.AWAITING_LANGUAGE,
            ConversationState.AWAITING_CERTIFICATE_NAME,
        ):
            await self.handle_progress(user, conversation)
            return self._outbox

        state = conversation.current_state
        if state == ConversationState.NEW_USER:
            await self.handle_new_user(user, conversation)
        elif state == ConversationState.AWAITING_LANGUAGE:
            await self.handle_language_selection(user, conversation, interactive_id or message_text)
        elif state == ConversationState.IN_LESSON:
            await self.handle_lesson_flow(user, conversation, message_text)
        elif state == ConversationState.AWAITING_QUIZ:
            await self.handle_quiz_response(user, conversation, interactive_id or message_text)
        elif state == ConversationState.DAY_COMPLETE:
            await self.handle_day_complete(user, conversation, message_text)
        elif state == ConversationState.AWAITING_CERTIFICATE_NAME:
            await self.handle_certificate_name(user, conversation, message_text)
        elif state == ConversationState.PROGRAM_COMPLETE:
            await self.handle_program_complete(user, conversation)
        else:
            await self.handle_new_user(user, conversation)

        await self.db.commit()
        return self._outbox

    @staticmethod
    def _typed_answer_to_button(conversation: Conversation, text: str) -> Optional[str]:
        """'A'..'D' or '1'..'4' typed during a quiz -> the matching ans_ button id."""
        t = text.strip().upper()
        if t in ("A", "B", "C", "D"):
            pos = ord(t) - 65
        elif t in ("1", "2", "3", "4"):
            pos = int(t) - 1
        else:
            return None
        q = (conversation.context or {}).get("current_question", 0)
        return f"ans_{q}_{pos}"

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def handle_new_user(self, user: User, conversation: Conversation) -> None:
        """NEW_USER: welcome + language selection. No name arg — we don't
        collect a real name until Day 7, so user.name is a placeholder here."""
        self._emit(conversation, self.builder.build_welcome_message())
        self._emit(conversation, self.builder.build_language_selector())
        conversation.current_state = ConversationState.AWAITING_LANGUAGE
        await self.db.commit()

    async def handle_language_selection(self, user: User, conversation: Conversation, selection: str) -> None:
        selected_language = LANGUAGE_MAP.get(selection)
        if not selected_language:
            self._emit(conversation, self.builder.build_language_selector())
            await self.db.commit()
            return

        context = conversation.context or {}
        # Mid-flow language change — confirm first (only if there is real progress)
        has_progress = user.current_day > 1 or conversation.previous_state not in (
            None, ConversationState.NEW_USER, ConversationState.AWAITING_LANGUAGE
        )
        if context.get("pending_language_change") and user.language != selected_language and has_progress:
            conversation.context = {**context, "confirming_language_change": selected_language.value}
            self._emit(conversation, OutboundMessage(
                kind="choice",
                text=(
                    f"⚠️ *Switching to {LANGUAGE_NAMES[selected_language]}*\n\n"
                    f"Your lessons will restart from Day {user.current_day} in the new language.\n"
                    "Your quiz scores won't transfer.\n\n"
                    "Reply *YES* to confirm or *NO* to cancel."
                ),
                buttons=[
                    self._btn("yes", "✅ Yes, switch"),
                    self._btn("no", "↩️ No, cancel"),
                ],
            ))
            await self.db.commit()
            return

        # First-time selection or same language — apply immediately
        user.language = selected_language
        conversation.current_state = ConversationState.IN_LESSON
        conversation.context = {}
        await self.db.commit()
        await self.deliver_next_lesson(user, conversation)

    async def handle_language_change_confirmation(self, user: User, conversation: Conversation, response: str) -> None:
        context = conversation.context or {}
        pending_lang = context.get("confirming_language_change")

        if response == "YES" and pending_lang:
            user.language = Language(pending_lang)
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(user, conversation)
        else:
            saved = context.get("saved_context") or {}
            conversation.current_state = conversation.previous_state or ConversationState.IN_LESSON
            conversation.context = {
                k: v for k, v in saved.items()
                if k not in ("pending_language_change", "saved_context", "confirming_language_change")
            }
            self._emit(conversation, OutboundMessage.text_only(
                "✅ Language change cancelled. Continuing in your current language."
            ))
            await self.db.commit()

    async def handle_continue(self, user: User, conversation: Conversation) -> None:
        """Resume the learner's current step regardless of where they stopped."""
        context = conversation.context or {}
        if conversation.current_state == ConversationState.AWAITING_QUIZ:
            lesson_id = context.get("current_lesson_id")
            current_question = context.get("current_question", 0)
            if lesson_id:
                lesson = await self._get_lesson(lesson_id)
                if lesson and current_question < len(lesson.quiz):
                    await self._resend_question(conversation, lesson, current_question)
                    await self.db.commit()
                    return
            # Corrupted context — fall back to lesson delivery
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(user, conversation)
        elif conversation.current_state == ConversationState.DAY_COMPLETE:
            if user.current_day < 7:
                await self.handle_day_complete(user, conversation, "NEXT")
            else:
                await self.handle_certificate_request(user, conversation)
        else:
            # IN_LESSON: get_next_lesson returns the first uncompleted lesson,
            # so this re-sends the lesson the learner stopped at
            await self.deliver_next_lesson(user, conversation)

    async def handle_progress(self, user: User, conversation: Conversation) -> None:
        progress = await self.lesson_manager.get_user_progress(user.id)
        if progress:
            self._emit(conversation, self.builder.build_progress_message(
                progress.current_day, progress.lessons_completed,
                progress.total_lessons, progress.completion_percentage,
            ))
        await self.db.commit()

    async def deliver_next_lesson(self, user: User, conversation: Conversation) -> None:
        next_lesson = await self.lesson_manager.get_next_lesson(user.id, user.language.value)

        if not next_lesson:
            await self.handle_day_completion(user, conversation)
            return

        # Lesson number (1-5) using the canonical topic order
        topic_order = self.lesson_manager.TOPIC_ORDER
        result = await self.db.execute(
            select(Lesson).where(Lesson.day == user.current_day, Lesson.language == user.language.value)
        )
        day_lessons = sorted(
            result.scalars().all(),
            key=lambda lesson: topic_order.index(lesson.topic) if lesson.topic in topic_order else 99,
        )
        lesson_number = day_lessons.index(next_lesson) + 1

        self._emit(conversation, self.builder.build_lesson_message(next_lesson, lesson_number))
        conversation.context = {"current_lesson_id": next_lesson.id}
        conversation.current_lesson_id = next_lesson.id
        conversation.current_state = ConversationState.IN_LESSON
        await self.db.commit()

    async def handle_lesson_flow(self, user: User, conversation: Conversation, message_text: str) -> None:
        """IN_LESSON: waiting for the learner to start the quiz."""
        context = conversation.context or {}
        if message_text.upper() in ("QUIZ", "RETRY"):
            lesson_id = context.get("current_lesson_id")
            if not lesson_id:
                await self.deliver_next_lesson(user, conversation)
                return

            lesson = await self._get_lesson(lesson_id)
            if lesson:
                # RETRY always starts from a fresh context, so retries get
                # re-randomized options too.
                order, shuffled_context = get_or_create_shuffle({}, 0, len(lesson.quiz[0]["options"]))
                self._emit(conversation, self.builder.build_quiz_message(lesson, 0, order))
                conversation.current_state = ConversationState.AWAITING_QUIZ
                conversation.context = {
                    **shuffled_context,
                    "current_lesson_id": lesson_id,
                    "current_question": 0,
                    "answers": [],
                }
                await self.db.commit()
        else:
            # No lesson on record means the learner never actually received
            # one — re-deliver on any reply instead of nagging about a quiz
            # for a lesson they never saw.
            if not context.get("current_lesson_id"):
                await self.deliver_next_lesson(user, conversation)
                return
            self._emit(conversation, OutboundMessage(
                kind="text",
                text="Tap *Start quiz* or reply *QUIZ* when you're ready to test your knowledge! 📝",
                buttons=[self._btn("quiz", "📝 Start quiz")],
            ))
            await self.db.commit()

    async def _resend_question(self, conversation: Conversation, lesson: Lesson, question: int) -> None:
        """Re-send the current question in the same order the learner already saw."""
        order, new_context = get_or_create_shuffle(
            conversation.context or {}, question, len(lesson.quiz[question]["options"])
        )
        if new_context is not conversation.context:
            conversation.context = new_context
        self._emit(conversation, self.builder.build_quiz_message(lesson, question, order))

    async def handle_quiz_response(self, user: User, conversation: Conversation, response: str) -> None:
        """AWAITING_QUIZ: record one answer, ask the next question, or grade."""
        context = conversation.context or {}
        lesson_id = context.get("current_lesson_id")
        current_question = context.get("current_question", 0)

        if not lesson_id:
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(user, conversation)
            return

        display_position: Optional[int] = None
        if response and response.startswith("ans_"):
            parts = response.split("_")
            try:
                display_position = int(parts[2]) if len(parts) == 3 else None
            except (ValueError, IndexError):
                display_position = None

        if display_position is None:
            # Not an answer — re-send the current question, same order as before
            lesson = await self._get_lesson(lesson_id)
            if lesson and current_question < len(lesson.quiz):
                await self._resend_question(conversation, lesson, current_question)
            await self.db.commit()
            return

        # The button id encodes the DISPLAY position — unshuffle using the
        # order this question was actually shown in before recording.
        current_order, working_context = get_or_create_shuffle(context, current_question, 4)
        if display_position >= len(current_order):
            lesson = await self._get_lesson(lesson_id)
            if lesson and current_question < len(lesson.quiz):
                await self._resend_question(conversation, lesson, current_question)
            await self.db.commit()
            return
        answer_idx = unshuffle_answer(display_position, current_order)

        answers = list(working_context.get("answers", []))
        answers.append(answer_idx)

        if current_question < 4:
            next_question = current_question + 1
            lesson = await self._get_lesson(lesson_id)
            next_order, shuffled_context = get_or_create_shuffle(
                working_context, next_question,
                len(lesson.quiz[next_question]["options"]) if lesson else 4,
            )
            conversation.context = {
                **shuffled_context,
                "current_question": next_question,
                "answers": answers,
            }
            if lesson:
                self._emit(conversation, self.builder.build_quiz_message(lesson, next_question, next_order))
            await self.db.commit()
        else:
            quiz_result = await self.lesson_manager.record_quiz_attempt(user.id, lesson_id, answers)
            self._emit(conversation, self.builder.build_quiz_result_message(
                quiz_result.score, quiz_result.passed, quiz_result.attempt_number, quiz_result.can_retry
            ))

            if quiz_result.passed:
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {}
                await self.db.commit()
                await self.deliver_next_lesson(user, conversation)
            else:
                # Keep lesson_id so RETRY re-triggers the same lesson
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {"current_lesson_id": lesson_id}
                await self.db.commit()

    async def handle_day_completion(self, user: User, conversation: Conversation) -> None:
        # The single point where every day's completion (1-7) is recorded
        await self.lesson_manager.mark_day_complete(user.id, user.current_day)
        progress = await self.lesson_manager.get_user_progress(user.id)

        # Only ask for the certificate name once, right here
        needs_name = user.current_day == 7 and not user.name_confirmed

        self._emit(conversation, self.builder.build_day_complete_message(
            user.current_day, progress.current_day_progress, needs_name=needs_name
        ))
        conversation.current_state = (
            ConversationState.AWAITING_CERTIFICATE_NAME if needs_name else ConversationState.DAY_COMPLETE
        )
        await self.db.commit()

    async def handle_certificate_name(self, user: User, conversation: Conversation, message_text: str) -> None:
        candidate = message_text.strip()
        if len(candidate) < 2 or len(candidate) > 255 or candidate.lower() in RESERVED_NAME_WORDS:
            self._emit(conversation, OutboundMessage.text_only(
                "Please reply with the full name you'd like printed on your certificate."
            ))
            await self.db.commit()
            return

        user.name = candidate
        user.name_confirmed = True
        await self.db.commit()

        self._emit(conversation, OutboundMessage.text_only(
            f"Got it — your certificate will say *{candidate}*. Generating it now..."
        ))
        await self.generate_and_send_certificate(user, conversation)

    async def handle_certificate_request(self, user: User, conversation: Conversation) -> None:
        """CERTIFICATE command, reachable from any state (natural Day 7 flow,
        or a returning learner who finished before names were collected)."""
        if user.completed_days < 7:
            self._emit(conversation, OutboundMessage.text_only(
                f"You're on Day {user.current_day}/7 — finish all 7 days to unlock your certificate! 💪"
            ))
            await self.db.commit()
            return

        if not user.name_confirmed:
            conversation.current_state = ConversationState.AWAITING_CERTIFICATE_NAME
            self._emit(conversation, OutboundMessage.text_only(
                "🎓 You're eligible for your certificate! What name should appear on it? Reply with your full name."
            ))
            await self.db.commit()
            return

        await self.generate_and_send_certificate(user, conversation)

    async def generate_and_send_certificate(self, user: User, conversation: Conversation) -> None:
        """Generate (or fetch the already-issued) certificate and send the link.
        generate_and_store_certificate is idempotent."""
        from app.certificates.generator import CertificateGenerator

        generator = CertificateGenerator(self.db, self.settings)
        try:
            certificate = await generator.generate_and_store_certificate(
                user_id=user.id, language=user.language.value
            )
        except Exception as e:  # noqa: BLE001 — surfaced to the learner, logged for ops
            logger.error("Certificate generation failed for user %s: %s", user.id, e)
            self._emit(conversation, OutboundMessage(
                kind="text",
                text="⚠️ We couldn't generate your certificate right now. Please tap *Get certificate* to try again in a few minutes.",
                buttons=[self._btn("certificate", "🎓 Get certificate")],
            ))
            await self.db.commit()
            return

        conversation.current_state = ConversationState.PROGRAM_COMPLETE
        if not certificate.is_verified:
            await self.send_certificate_paywall(user, conversation)
            return
        verify_url = (
            f"{self.settings.FRONTEND_URL}/verify"
            f"?code={certificate.certificate_id}&name={quote(user.name)}"
        )
        self._emit(conversation, self.builder.build_certificate_message(
            user.name, certificate.certificate_id, verify_url
        ))
        await self.db.commit()

    async def send_certificate_paywall(self, user: User, conversation: Conversation) -> None:
        """Earned but not yet unlocked: offer checkout (or a sponsor code)."""
        from app.services.payments import format_naira, start_certificate_payment
        from app.services.paystack import PaystackError

        price = format_naira(self.settings.CERTIFICATE_PRICE_KOBO)
        try:
            payment = await start_certificate_payment(self.db, self.settings, user)
        except PaystackError as e:
            logger.error("Certificate checkout unavailable for user %s: %s", user.id, e)
            self._emit(conversation, OutboundMessage(
                kind="text",
                text=(
                    f"🎓 You've earned your certificate! Unlocking the verified copy costs {price}, "
                    "but payments are unavailable right now. Please tap *Get certificate* again later.\n\n"
                    "Have a sponsor code? Reply *CODE* followed by the code."
                ),
                buttons=[self._btn("certificate", "🎓 Get certificate")],
            ))
            await self.db.commit()
            return

        from app.engine.messages import Button
        self._emit(conversation, OutboundMessage(
            kind="payment",
            text=(
                f"🎓 Well done, {user.name}! You've earned your MNAIR certificate.\n\n"
                f"Unlock your *verified certificate* for {price}. You'll get a PDF that employers "
                "can check online.\n"
                "Pay by card, bank transfer or USSD.\n\n"
                "After paying, tap *Get certificate*.\n"
                "Have a sponsor code? Reply *CODE* followed by the code."
            ),
            buttons=[
                Button("pay_link", f"💳 Pay {price}", payment.authorization_url or ""),
                self._btn("certificate", "🎓 Get certificate"),
            ],
            meta={"reference": payment.reference, "url": payment.authorization_url, "amount_kobo": payment.amount_kobo},
        ))
        await self.db.commit()

    async def handle_sponsor_code(self, user: User, conversation: Conversation, raw_code: str) -> None:
        from app.services.sponsorship import SponsorCodeError, redeem_code

        try:
            result = await redeem_code(self.db, user, raw_code)
        except SponsorCodeError as e:
            self._emit(conversation, OutboundMessage.text_only(f"⚠️ {e}"))
            return
        name = result.organization.name
        if result.already_applied:
            text = f"✅ You're already sponsored by *{name}*."
        else:
            text = f"✅ Code accepted! Your course and certificate are sponsored by *{name}*."
        self._emit(conversation, OutboundMessage.text_only(text))

        # A learner who was waiting at the paywall gets the certificate now
        if user.completed_days >= 7 and user.name_confirmed and conversation.current_state == ConversationState.PROGRAM_COMPLETE:
            await self.generate_and_send_certificate(user, conversation)

    async def handle_day_complete(self, user: User, conversation: Conversation, message_text: str) -> None:
        """DAY_COMPLETE: waiting for the learner to advance."""
        if message_text.upper() == "NEXT":
            advanced = await self.lesson_manager.advance_to_next_day(user.id)
            if advanced:
                await self.db.refresh(user)
                conversation.current_state = ConversationState.IN_LESSON
                await self.db.commit()
                await self.deliver_next_lesson(user, conversation)
            else:
                self._emit(conversation, OutboundMessage.text_only(
                    "❌ Couldn't advance to next day. Please ensure all lessons are complete."
                ))
                await self.db.commit()
        else:
            if user.current_day < 7:
                self._emit(conversation, OutboundMessage(
                    kind="text",
                    text=f"🎊 You've completed Day {user.current_day}!\n\nTap *Next day* or reply *NEXT* to continue!",
                    buttons=[self._btn("next", f"➡️ Next: Day {user.current_day + 1}")],
                ))
            else:
                self._emit(conversation, OutboundMessage(
                    kind="text",
                    text=f"🎊 You've completed Day {user.current_day}!\n\nTap *Get certificate* or reply *CERTIFICATE* to claim your certificate!",
                    buttons=[self._btn("certificate", "🎓 Get certificate")],
                ))
            await self.db.commit()

    async def handle_program_complete(self, user: User, conversation: Conversation) -> None:
        self._emit(conversation, OutboundMessage(
            kind="text",
            text=(
                "🎓 You've completed the full MNAIR course — well done!\n\n"
                "Tap *Get certificate* any time to get your certificate link again, "
                "or reply *LANGUAGE* to take the course again in another language."
            ),
            buttons=[self._btn("certificate", "🎓 Get certificate"), self._btn("language", "🌍 Change language")],
        ))
        await self.db.commit()

    @staticmethod
    def _btn(id_: str, title: str):
        from app.engine.messages import Button
        return Button(id_, title)
