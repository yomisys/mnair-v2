"""
WhatsApp Channel Handler for MNAIR Platform
Handles Meta WhatsApp Business API webhooks and conversation flow
"""

from __future__ import annotations
import hmac
import hashlib
import json
from typing import Dict, Optional, List, Any
from datetime import datetime
from enum import Enum

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, Language
from app.models.conversation import Conversation, ConversationState
from app.models.lesson import Lesson
from app.services.lesson_state import LessonStateManager
from app.config import Settings, get_settings


class MessageType(str, Enum):
    """WhatsApp message types"""
    TEXT = "text"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    IMAGE = "image"


class WhatsAppMessageBuilder:
    """
    Builds WhatsApp messages using Meta's Cloud API format
    Optimized for Nigerian bandwidth (<50KB images, <1600 chars)
    """

    @staticmethod
    def build_welcome_message(name: Optional[str] = None) -> Dict[str, Any]:
        """Build welcome message for new users"""
        greeting = f"Hello {name}! " if name else "Hello! "

        return {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": f"{greeting}🎓 Welcome to Make Nigeria AI Ready (MNAIR)!\n\n"
                        f"Learn Artificial Intelligence in 7 days - for FREE!\n\n"
                        f"📱 Study at your own pace\n"
                        f"🎯 5 topics per day\n"
                        f"📜 Get a certificate when you finish\n\n"
                        f"Ready to start your AI journey?"
            }
        }

    @staticmethod
    def build_language_selector() -> Dict[str, Any]:
        """Build language selection interactive buttons"""
        return {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": "Choose your preferred language:\n\n"
                            "Select the language you're most comfortable with:"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "lang_en",
                                "title": "🇬🇧 English"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "lang_pid",
                                "title": "🇳🇬 Pidgin"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "lang_ha",
                                "title": "🇳🇬 Hausa"
                            }
                        }
                    ]
                }
            }
        }

    @staticmethod
    def build_language_selector_list() -> Dict[str, Any]:
        """Build complete language selection with list (for 5 languages)"""
        return {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "Choose your preferred language:\n\n"
                            "Select the language you're most comfortable with for learning."
                },
                "action": {
                    "button": "Select Language",
                    "sections": [
                        {
                            "title": "Available Languages",
                            "rows": [
                                {
                                    "id": "lang_en",
                                    "title": "English",
                                    "description": "Learn in English"
                                },
                                {
                                    "id": "lang_pid",
                                    "title": "Pidgin",
                                    "description": "Learn for Naija Pidgin"
                                },
                                {
                                    "id": "lang_ha",
                                    "title": "Hausa",
                                    "description": "Koyi cikin Hausa"
                                },
                                {
                                    "id": "lang_yo",
                                    "title": "Yoruba",
                                    "description": "Kọ ẹkọ ni ede Yoruba"
                                },
                                {
                                    "id": "lang_ig",
                                    "title": "Igbo",
                                    "description": "Mụta n'asụsụ Igbo"
                                }
                            ]
                        }
                    ]
                }
            }
        }

    @staticmethod
    def build_lesson_message(lesson: Lesson, lesson_number: int, total: int = 5) -> Dict[str, Any]:
        """Build lesson delivery message"""
        # Truncate content if too long (WhatsApp limit 1600 chars)
        content = lesson.content
        if len(content) > 1400:
            content = content[:1400] + "..."

        message_text = (
            f"📚 Day {lesson.day} - Lesson {lesson_number}/{total}\n"
            f"{'='*30}\n\n"
            f"*{lesson.title}*\n\n"
            f"{content}\n\n"
            f"{'='*30}\n"
            f"Ready for the quiz? Reply *QUIZ* to start!"
        )

        return {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": message_text,
                "preview_url": False
            }
        }

    @staticmethod
    def build_quiz_message(lesson: Lesson, question_num: int) -> Dict[str, Any]:
        """Build quiz question with interactive buttons"""
        if not lesson.quiz or question_num >= len(lesson.quiz):
            raise ValueError(f"Invalid question number {question_num}")

        quiz_item = lesson.quiz[question_num]
        question_text = quiz_item["question"]
        options = quiz_item["options"]

        # Build buttons (max 3 buttons, so we'll use list for 4 options)
        return {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": f"❓ Question {question_num + 1}/5\n\n{question_text}"
                },
                "action": {
                    "button": "Choose Answer",
                    "sections": [
                        {
                            "title": "Select your answer",
                            "rows": [
                                {
                                    "id": f"ans_{question_num}_{i}",
                                    "title": f"Option {chr(65+i)}",
                                    "description": opt[:72]  # WhatsApp description limit
                                }
                                for i, opt in enumerate(options)
                            ]
                        }
                    ]
                }
            }
        }

    @staticmethod
    def build_quiz_result_message(score: float, passed: bool, attempt: int, can_retry: bool) -> Dict[str, Any]:
        """Build quiz result message"""
        if passed:
            emoji = "🎉"
            status = "PASSED!"
            message = (
                f"{emoji} *Congratulations!*\n\n"
                f"You scored {score:.0f}% on your quiz!\n"
                f"Attempt: {attempt}/3\n\n"
                f"✅ Lesson completed! Moving to next lesson..."
            )
        else:
            emoji = "😔"
            status = "Not quite there yet"
            retry_msg = "\n\n📝 Reply *RETRY* to try again!" if can_retry else "\n\n❌ Maximum attempts reached."
            message = (
                f"{emoji} *{status}*\n\n"
                f"You scored {score:.0f}%\n"
                f"You need 60% to pass (3/5 correct)\n"
                f"Attempt: {attempt}/3"
                f"{retry_msg}"
            )

        return {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": message
            }
        }

    @staticmethod
    def build_day_complete_message(day: int, lessons_completed: int) -> Dict[str, Any]:
        """Build day completion celebration message"""
        return {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": (
                    f"🎊 *DAY {day} COMPLETE!* 🎊\n\n"
                    f"Congratulations! You've finished all {lessons_completed} lessons for Day {day}!\n\n"
                    f"📈 Your Progress:\n"
                    f"✅ Day {day} - DONE\n"
                    f"📚 {lessons_completed} lessons completed\n\n"
                    f"{'🏆 Keep going! Only ' + str(7 - day) + ' days left!' if day < 7 else '🎓 COURSE COMPLETE! Certificate coming soon!'}\n\n"
                    f"{'Reply *NEXT* to continue to Day ' + str(day + 1) + '!' if day < 7 else 'Reply *CERTIFICATE* to get your certificate!'}"
                )
            }
        }

    @staticmethod
    def build_progress_message(current_day: int, lessons_completed: int, total_lessons: int, completion_pct: float) -> Dict[str, Any]:
        """Build progress summary message"""
        progress_bar = "█" * int(completion_pct / 10) + "░" * (10 - int(completion_pct / 10))

        return {
            "messaging_product": "whatsapp",
            "type": "text",
            "text": {
                "body": f"📊 *Your Progress*\n\n"
                        f"Current Day: *{current_day}/7*\n"
                        f"Lessons Completed: *{lessons_completed}/{total_lessons}*\n\n"
                        f"Progress: {progress_bar} {completion_pct:.1f}%\n\n"
                        f"Keep it up! 🚀"
            }
        }


class WhatsAppWebhookHandler:
    """
    Handles WhatsApp webhook events and conversation state management
    Implements state machine for lesson delivery flow
    """

    def __init__(self, settings: Settings, db: AsyncSession):
        """
        Initialize webhook handler

        Args:
            settings: Application settings
            db: Database session
        """
        self.settings = settings
        self.db = db
        self.message_builder = WhatsAppMessageBuilder()
        self.lesson_manager = LessonStateManager(db)

    async def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Meta webhook signature

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header

        Returns:
            True if signature is valid
        """
        if not self.settings.META_WEBHOOK_SECRET:
            # Skip verification in development
            return True

        expected_signature = hmac.new(
            self.settings.META_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Signature format: "sha256=<hash>"
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(expected_signature, signature)

    async def send_whatsapp_message(self, phone_number: str, message: Dict[str, Any]) -> bool:
        """
        Send message via Meta WhatsApp Cloud API

        Args:
            phone_number: Recipient phone number
            message: Message payload

        Returns:
            True if sent successfully
        """
        if not self.settings.META_WHATSAPP_TOKEN:
            print(f"[DEV MODE] Would send to {phone_number}: {message}")
            return True

        url = f"https://graph.facebook.com/v18.0/{self.settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages"

        headers = {
            "Authorization": f"Bearer {self.settings.META_WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "to": phone_number,
            **message
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                response.raise_for_status()
                return True
            except httpx.HTTPError as e:
                print(f"[ERROR] Failed to send WhatsApp message: {e}")
                return False

    async def get_or_create_user(self, phone_number: str, name: Optional[str] = None) -> User:
        """
        Get existing user or create new one

        Args:
            phone_number: User phone number
            name: User name (optional)

        Returns:
            User object
        """
        # Check if user exists
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()

        if not user:
            # Create new user
            user = User(
                phone_number=phone_number,
                name=name or "WhatsApp User",
                language=Language.ENGLISH,  # Default, will be updated
                current_day=1,
                preferred_channel="whatsapp",
                consent_given=True,  # Implied by using the service
                data_retention_date=datetime.utcnow()
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

        return user

    async def get_or_create_conversation(self, user_id: int, phone_number: str) -> Conversation:
        """
        Get active conversation or create new one

        Args:
            user_id: User ID
            phone_number: User phone number

        Returns:
            Conversation object
        """
        # Check for active conversation
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.channel == "whatsapp",
                Conversation.is_active == True
            )
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            # Create new conversation
            conversation = Conversation(
                user_id=user_id,
                channel="whatsapp",
                phone_number=phone_number,
                current_state=ConversationState.NEW_USER,
                is_active=True
            )
            self.db.add(conversation)
            await self.db.commit()
            await self.db.refresh(conversation)

        return conversation

    async def handle_message(self, phone_number: str, message_text: str, message_type: str = "text", interactive_id: Optional[str] = None) -> None:
        """
        Main message handler - routes to appropriate state handler

        Args:
            phone_number: Sender phone number
            message_text: Message text
            message_type: Type of message (text, interactive)
            interactive_id: ID of interactive button/list response
        """
        # Get or create user
        user = await self.get_or_create_user(phone_number)

        # Get or create conversation
        conversation = await self.get_or_create_conversation(user.id, phone_number)

        # Global command: change language from anywhere
        if message_text.upper() == "LANGUAGE":
            conversation.context = {
                **conversation.context,
                "pending_language_change": True,
                "saved_context": conversation.context,  # preserve lesson position for NO cancellation
            }
            conversation.previous_state = conversation.current_state
            conversation.current_state = ConversationState.AWAITING_LANGUAGE
            await self.db.commit()
            await self.send_whatsapp_message(phone_number, self.message_builder.build_language_selector_list())
            return

        # Handle YES/NO confirmation for language change
        if message_text.upper() in ("YES", "NO") and conversation.context.get("confirming_language_change"):
            await self.handle_language_change_confirmation(user, conversation, message_text.upper())
            return

        # Route to state handler
        if conversation.current_state == ConversationState.NEW_USER:
            await self.handle_new_user(user, conversation)
        elif conversation.current_state == ConversationState.AWAITING_LANGUAGE:
            await self.handle_language_selection(user, conversation, interactive_id or message_text)
        elif conversation.current_state == ConversationState.IN_LESSON:
            await self.handle_lesson_flow(user, conversation, message_text)
        elif conversation.current_state == ConversationState.AWAITING_QUIZ:
            await self.handle_quiz_response(user, conversation, interactive_id or message_text)
        elif conversation.current_state == ConversationState.DAY_COMPLETE:
            await self.handle_day_complete(user, conversation, message_text)
        else:
            # Unknown state, reset
            await self.handle_new_user(user, conversation)

    async def handle_new_user(self, user: User, conversation: Conversation) -> None:
        """Handle NEW_USER state - send welcome and language selection"""
        # Send welcome message
        welcome_msg = self.message_builder.build_welcome_message(user.name)
        await self.send_whatsapp_message(user.phone_number, welcome_msg)

        # Send language selector
        lang_msg = self.message_builder.build_language_selector_list()
        await self.send_whatsapp_message(user.phone_number, lang_msg)

        # Update conversation state
        conversation.current_state = ConversationState.AWAITING_LANGUAGE
        await self.db.commit()

    async def handle_language_selection(self, user: User, conversation: Conversation, selection: str) -> None:
        """Handle AWAITING_LANGUAGE state - process language choice"""
        language_map = {
            "lang_en": Language.ENGLISH,
            "lang_pid": Language.PIDGIN,
            "lang_ha": Language.HAUSA,
            "lang_yo": Language.YORUBA,
            "lang_ig": Language.IGBO,
        }

        selected_language = language_map.get(selection)
        if not selected_language:
            await self.send_whatsapp_message(user.phone_number, self.message_builder.build_language_selector_list())
            return

        # Mid-flow language change — ask for confirmation first (only if user has actual progress)
        has_progress = user.current_day > 1 or conversation.previous_state not in (None, ConversationState.NEW_USER, ConversationState.AWAITING_LANGUAGE)
        if conversation.context.get("pending_language_change") and user.language != selected_language and has_progress:
            language_names = {
                Language.ENGLISH: "English", Language.PIDGIN: "Pidgin",
                Language.HAUSA: "Hausa", Language.YORUBA: "Yoruba", Language.IGBO: "Igbo",
            }
            conversation.context = {
                **conversation.context,
                "confirming_language_change": selected_language.value,
            }
            await self.db.commit()
            await self.send_whatsapp_message(user.phone_number, {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {
                    "body": (
                        f"⚠️ *Switching to {language_names[selected_language]}*\n\n"
                        f"Your lessons will restart from Day {user.current_day} in the new language.\n"
                        f"Your quiz scores won't transfer.\n\n"
                        f"Reply *YES* to confirm or *NO* to cancel."
                    )
                }
            })
            return

        # First-time selection or same language — apply immediately
        user.language = selected_language
        conversation.current_state = ConversationState.IN_LESSON
        conversation.context = {}
        await self.db.commit()
        await self.deliver_next_lesson(user, conversation)

    async def handle_language_change_confirmation(self, user: User, conversation: Conversation, response: str) -> None:
        """Handle YES/NO confirmation for mid-flow language change"""
        pending_lang = conversation.context.get("confirming_language_change")

        if response == "YES" and pending_lang:
            user.language = Language(pending_lang)
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(user, conversation)
        else:
            # Restore previous state and context
            saved = conversation.context.get("saved_context") or {}
            conversation.current_state = conversation.previous_state or ConversationState.IN_LESSON
            conversation.context = {k: v for k, v in saved.items() if k not in ("pending_language_change", "saved_context", "confirming_language_change")}
            await self.db.commit()
            await self.send_whatsapp_message(user.phone_number, {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {"body": "✅ Language change cancelled. Continuing in your current language."}
            })

    async def deliver_next_lesson(self, user: User, conversation: Conversation) -> None:
        """Deliver the next lesson to user"""
        # Get next lesson
        next_lesson = await self.lesson_manager.get_next_lesson(user.id, user.language.value)

        if not next_lesson:
            # Day complete!
            await self.handle_day_completion(user, conversation)
            return

        # Calculate lesson number (1-5) using the canonical topic order
        topic_order = self.lesson_manager.TOPIC_ORDER
        result = await self.db.execute(
            select(Lesson).where(
                Lesson.day == user.current_day,
                Lesson.language == user.language.value
            )
        )
        day_lessons = sorted(
            result.scalars().all(),
            key=lambda l: topic_order.index(l.topic) if l.topic in topic_order else 99
        )
        lesson_number = day_lessons.index(next_lesson) + 1

        # Send lesson
        lesson_msg = self.message_builder.build_lesson_message(next_lesson, lesson_number)
        await self.send_whatsapp_message(user.phone_number, lesson_msg)

        # Store current lesson in conversation context
        conversation.context = {"current_lesson_id": next_lesson.id}
        conversation.current_state = ConversationState.IN_LESSON
        await self.db.commit()

    async def handle_lesson_flow(self, user: User, conversation: Conversation, message_text: str) -> None:
        """Handle IN_LESSON state - waiting for user to request quiz"""
        if message_text.upper() in ("QUIZ", "RETRY"):
            # Start quiz
            lesson_id = conversation.context.get("current_lesson_id")
            if not lesson_id:
                # No lesson in context, deliver next
                await self.deliver_next_lesson(user, conversation)
                return

            # Get lesson
            result = await self.db.execute(
                select(Lesson).where(Lesson.id == lesson_id)
            )
            lesson = result.scalar_one_or_none()

            if lesson:
                # Send first quiz question
                quiz_msg = self.message_builder.build_quiz_message(lesson, 0)
                await self.send_whatsapp_message(user.phone_number, quiz_msg)

                # Update state
                conversation.current_state = ConversationState.AWAITING_QUIZ
                conversation.context = {
                    "current_lesson_id": lesson_id,
                    "current_question": 0,
                    "answers": []
                }
                await self.db.commit()
        else:
            # Remind user to start quiz
            reminder = {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {
                    "body": "Reply *QUIZ* when you're ready to test your knowledge! 📝"
                }
            }
            await self.send_whatsapp_message(user.phone_number, reminder)

    async def handle_quiz_response(self, user: User, conversation: Conversation, response: str) -> None:
        """Handle AWAITING_QUIZ state - process quiz answers"""
        lesson_id = conversation.context.get("current_lesson_id")
        current_question = conversation.context.get("current_question", 0)

        # Guard: corrupted context — recover gracefully
        if not lesson_id:
            conversation.current_state = ConversationState.IN_LESSON
            conversation.context = {}
            await self.db.commit()
            await self.deliver_next_lesson(user, conversation)
            return

        if response.startswith("ans_"):
            parts = response.split("_")
            try:
                answer_idx = int(parts[2]) if len(parts) == 3 else None
            except (ValueError, IndexError):
                answer_idx = None
            if answer_idx is None:
                # Malformed ans_ — re-send current question
                result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
                lesson = result.scalar_one_or_none()
                if lesson:
                    await self.send_whatsapp_message(user.phone_number, self.message_builder.build_quiz_message(lesson, current_question))
                return
        else:
            # Non-interactive reply — re-send current question
            result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
            lesson = result.scalar_one_or_none()
            if lesson:
                await self.send_whatsapp_message(user.phone_number, self.message_builder.build_quiz_message(lesson, current_question))
            return

        answers = conversation.context.get("answers", [])
        answers.append(answer_idx)

        # Replace the entire dict so SQLAlchemy detects the JSON column change
        if current_question < 4:
            next_question = current_question + 1
            conversation.context = {
                **conversation.context,
                "current_question": next_question,
                "answers": answers,
            }
            await self.db.commit()

            result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
            lesson = result.scalar_one_or_none()
            if lesson:
                await self.send_whatsapp_message(user.phone_number, self.message_builder.build_quiz_message(lesson, next_question))
        else:
            # Quiz complete — score it
            quiz_result = await self.lesson_manager.record_quiz_attempt(user.id, lesson_id, answers)

            result_msg = self.message_builder.build_quiz_result_message(
                quiz_result.score, quiz_result.passed, quiz_result.attempt_number, quiz_result.can_retry
            )
            await self.send_whatsapp_message(user.phone_number, result_msg)

            if quiz_result.passed:
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {}
                await self.db.commit()
                await self.deliver_next_lesson(user, conversation)
            else:
                # Keep lesson_id so QUIZ re-triggers the same lesson, not deliver_next_lesson
                conversation.current_state = ConversationState.IN_LESSON
                conversation.context = {"current_lesson_id": lesson_id}
                await self.db.commit()

    async def handle_day_completion(self, user: User, conversation: Conversation) -> None:
        """Handle day completion celebration"""
        # Get progress
        progress = await self.lesson_manager.get_user_progress(user.id)

        # Send celebration message
        celebration_msg = self.message_builder.build_day_complete_message(
            user.current_day, progress.current_day_progress
        )
        await self.send_whatsapp_message(user.phone_number, celebration_msg)

        # Update conversation state
        conversation.current_state = ConversationState.DAY_COMPLETE
        await self.db.commit()

    async def handle_day_complete(self, user: User, conversation: Conversation, message_text: str) -> None:
        """Handle DAY_COMPLETE state - waiting for user to advance"""
        cmd = message_text.upper()

        if cmd == "NEXT":
            advanced = await self.lesson_manager.advance_to_next_day(user.id)

            if advanced:
                await self.db.refresh(user)
                conversation.current_state = ConversationState.IN_LESSON
                await self.db.commit()
                await self.deliver_next_lesson(user, conversation)
            else:
                await self.send_whatsapp_message(user.phone_number, {
                    "messaging_product": "whatsapp",
                    "type": "text",
                    "text": {"body": "❌ Couldn't advance to next day. Please ensure all lessons are complete."}
                })
        elif cmd == "CERTIFICATE":
            await self.send_whatsapp_message(user.phone_number, {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {"body": "🎓 Your certificate is being generated! You'll receive it shortly."}
            })
        else:
            # Remind user what to do — no silent drop
            next_action = "Reply *NEXT* to continue!" if user.current_day < 7 else "Reply *CERTIFICATE* to claim your certificate!"
            await self.send_whatsapp_message(user.phone_number, {
                "messaging_product": "whatsapp",
                "type": "text",
                "text": {"body": f"🎊 You've completed Day {user.current_day}!\n\n{next_action}"}
            })


# FastAPI Router for WhatsApp webhooks
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
async def verify_webhook(
    request: Request,
    settings: Settings = Depends(get_settings)
):
    """
    Verify WhatsApp webhook (Meta verification)
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def handle_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Handle incoming WhatsApp messages
    """
    # Get raw body for signature verification
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    # Verify signature
    handler = WhatsAppWebhookHandler(settings, db)
    if not await handler.verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    payload = json.loads(body)

    # Extract message data
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        message = messages[0]
        phone_number = message["from"]
        message_type = message["type"]

        # Extract message content
        if message_type == "text":
            message_text = message["text"]["body"]
            await handler.handle_message(phone_number, message_text, "text")
        elif message_type == "interactive":
            interactive = message["interactive"]
            if interactive["type"] == "list_reply":
                interactive_id = interactive["list_reply"]["id"]
                await handler.handle_message(phone_number, "", "interactive", interactive_id)
            elif interactive["type"] == "button_reply":
                interactive_id = interactive["button_reply"]["id"]
                await handler.handle_message(phone_number, "", "interactive", interactive_id)

        return {"status": "ok"}

    except (KeyError, IndexError) as e:
        print(f"[ERROR] Failed to parse webhook payload: {e}")
        return {"status": "error", "message": str(e)}
