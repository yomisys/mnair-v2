"""
USSD Channel Handler for MNAIR Platform
Handles Africa's Talking USSD sessions for feature phone access
"""

from __future__ import annotations
import json
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Request, Form, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.database import get_db
from app.models.user import User, Language
from app.models.lesson import Lesson
from app.services.lesson_state import LessonStateManager
from app.config import Settings, get_settings


class USSDMenuState(str, Enum):
    """USSD menu states"""
    MAIN_MENU = "main_menu"
    LANGUAGE_SELECTION = "language_selection"
    LESSON_DISPLAY = "lesson_display"
    QUIZ_QUESTION = "quiz_question"
    QUIZ_RESULT = "quiz_result"
    PROGRESS_DISPLAY = "progress_display"
    DAY_COMPLETE = "day_complete"


class USSDResponse:
    """USSD response builder"""

    @staticmethod
    def con(message: str) -> str:
        """Continue session - show message and wait for input"""
        return f"CON {message}"

    @staticmethod
    def end(message: str) -> str:
        """End session - show message and terminate"""
        return f"END {message}"


class ContentChunker:
    """
    Chunks long content into 160-character screens for USSD display
    """

    MAX_CHARS = 160

    @classmethod
    def chunk_text(cls, text: str, max_chars: int = MAX_CHARS) -> List[str]:
        """
        Split text into chunks that fit USSD screen limits

        Args:
            text: Full text to chunk
            max_chars: Maximum characters per chunk

        Returns:
            List of text chunks
        """
        # Remove extra whitespace
        text = " ".join(text.split())

        if len(text) <= max_chars:
            return [text]

        chunks = []
        current_chunk = ""

        # Split by sentences first
        sentences = text.replace(". ", ".|").split("|")

        for sentence in sentences:
            # If adding this sentence exceeds limit, save current chunk
            if len(current_chunk) + len(sentence) + 1 > max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # If single sentence is too long, split by words
                if len(sentence) > max_chars:
                    words = sentence.split()
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_chars:
                            chunks.append(current_chunk.strip())
                            current_chunk = word
                        else:
                            current_chunk += " " + word if current_chunk else word
                else:
                    current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    @classmethod
    def format_lesson_chunk(cls, chunk: str, chunk_num: int, total_chunks: int) -> str:
        """
        Format a lesson chunk with navigation info

        Args:
            chunk: Text chunk
            chunk_num: Current chunk number (0-indexed)
            total_chunks: Total number of chunks

        Returns:
            Formatted chunk with footer
        """
        footer = f"\n\n[{chunk_num + 1}/{total_chunks}]"
        if chunk_num < total_chunks - 1:
            footer += "\n1. Continue\n0. Main Menu"
        else:
            footer += "\n1. Take Quiz\n0. Main Menu"

        # Ensure total length fits
        max_content = cls.MAX_CHARS - len(footer)
        if len(chunk) > max_content:
            chunk = chunk[:max_content - 3] + "..."

        return chunk + footer


class USSDSessionManager:
    """
    Manages USSD session state in Redis with 90-second timeout
    """

    SESSION_TIMEOUT = 90  # seconds

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize session manager

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session data from Redis

        Args:
            session_id: Unique session identifier

        Returns:
            Session data dict or None
        """
        data = await self.redis.get(f"ussd:session:{session_id}")
        if data:
            return json.loads(data)
        return None

    async def save_session(self, session_id: str, data: Dict) -> None:
        """
        Save session data to Redis with timeout

        Args:
            session_id: Unique session identifier
            data: Session data to store
        """
        await self.redis.setex(
            f"ussd:session:{session_id}",
            self.SESSION_TIMEOUT,
            json.dumps(data)
        )

    async def clear_session(self, session_id: str) -> None:
        """
        Clear session data from Redis

        Args:
            session_id: Unique session identifier
        """
        await self.redis.delete(f"ussd:session:{session_id}")


class USSDHandler:
    """
    Main USSD handler for Africa's Talking integration
    Implements menu-driven lesson delivery for feature phones
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        settings: Settings
    ):
        """
        Initialize USSD handler

        Args:
            db: Database session
            redis_client: Redis client
            settings: Application settings
        """
        self.db = db
        self.session_mgr = USSDSessionManager(redis_client)
        self.settings = settings
        self.lesson_mgr = LessonStateManager(db)
        self.chunker = ContentChunker()

    async def handle_request(
        self,
        session_id: str,
        phone_number: str,
        text: str
    ) -> str:
        """
        Main request handler - routes to appropriate menu handler

        Args:
            session_id: Africa's Talking session ID
            phone_number: User phone number
            text: User input text (empty for new session)

        Returns:
            USSD response string (CON or END)
        """
        # Get or create session
        session = await self.session_mgr.get_session(session_id)

        if not session:
            # New session
            session = {
                "phone_number": phone_number,
                "state": USSDMenuState.MAIN_MENU,
                "user_id": None,
                "data": {}
            }

        # Parse user input
        inputs = text.split("*") if text else []
        current_input = inputs[-1] if inputs else ""

        # Get or create user
        user = await self.get_or_create_user(phone_number)
        session["user_id"] = user.id

        # Track activity — drives inactive-user reminder eligibility
        user.last_active_at = datetime.utcnow()
        await self.db.commit()

        # Route to appropriate handler
        state = session.get("state", USSDMenuState.MAIN_MENU)

        if state == USSDMenuState.MAIN_MENU:
            response = await self.handle_main_menu(user, session, current_input)
        elif state == USSDMenuState.LANGUAGE_SELECTION:
            response = await self.handle_language_selection(user, session, current_input)
        elif state == USSDMenuState.LESSON_DISPLAY:
            response = await self.handle_lesson_display(user, session, current_input)
        elif state == USSDMenuState.QUIZ_QUESTION:
            response = await self.handle_quiz_question(user, session, current_input)
        elif state == USSDMenuState.QUIZ_RESULT:
            response = await self.handle_quiz_result(user, session, current_input)
        elif state == USSDMenuState.PROGRESS_DISPLAY:
            response = await self.handle_progress_display(user, session, current_input)
        elif state == USSDMenuState.DAY_COMPLETE:
            response = await self.handle_day_complete(user, session, current_input)
        else:
            response = await self.show_main_menu()

        # Save session
        await self.session_mgr.save_session(session_id, session)

        return response

    async def get_or_create_user(self, phone_number: str) -> User:
        """Get existing user or create new one"""
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                phone_number=phone_number,
                name=f"USSD User {phone_number[-4:]}",
                language=Language.ENGLISH,
                current_day=1,
                preferred_channel="ussd",
                consent_given=True,
                data_retention_date=datetime.utcnow() + timedelta(days=90)
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

        return user

    async def show_main_menu(self) -> str:
        """Display main menu"""
        return USSDResponse.con(
            "Welcome to Make Nigeria AI Ready\n"
            "Learn AI in 7 days - FREE!\n\n"
            "1. Start Learning\n"
            "2. My Progress\n"
            "3. Get Certificate"
        )

    async def handle_main_menu(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle main menu selection"""
        if not choice:
            return await self.show_main_menu()

        if choice == "1":
            # Check if user has selected language
            if user.language == Language.ENGLISH and not session.get("data", {}).get("language_set"):
                # First time, show language selection
                session["state"] = USSDMenuState.LANGUAGE_SELECTION
                return await self.show_language_menu()
            else:
                # Start learning
                session["state"] = USSDMenuState.LESSON_DISPLAY
                session["data"] = {"chunk_index": 0}
                return await self.deliver_next_lesson(user, session)

        elif choice == "2":
            # Show progress
            session["state"] = USSDMenuState.PROGRESS_DISPLAY
            return await self.show_progress(user)

        elif choice == "3":
            # Certificate
            if user.current_day >= 7 and user.completed_days >= 7:
                host = self.settings.FRONTEND_URL.replace("https://", "").replace("http://", "")
                return USSDResponse.end(
                    "Congratulations!\n"
                    "You've completed the course!\n\n"
                    f"Visit {host} to download your certificate."
                )
            else:
                return USSDResponse.end(
                    f"Complete all 7 days to get your certificate.\n"
                    f"You're on Day {user.current_day}. Keep going!"
                )

        else:
            return USSDResponse.end("Invalid choice. Dial *384*8080# to try again.")

    async def show_language_menu(self) -> str:
        """Display language selection menu"""
        return USSDResponse.con(
            "Choose your language:\n\n"
            "1. English\n"
            "2. Pidgin\n"
            "3. Hausa\n"
            "4. Yoruba\n"
            "5. Igbo"
        )

    async def handle_language_selection(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle language selection"""
        language_map = {
            "1": Language.ENGLISH,
            "2": Language.PIDGIN,
            "3": Language.HAUSA,
            "4": Language.YORUBA,
            "5": Language.IGBO,
        }

        selected_language = language_map.get(choice)
        if not selected_language:
            return USSDResponse.end("Invalid choice. Dial *384*8080# to try again.")

        # Update user language
        user.language = selected_language
        await self.db.commit()

        # Mark language as set
        session["data"]["language_set"] = True
        session["state"] = USSDMenuState.LESSON_DISPLAY
        session["data"]["chunk_index"] = 0

        # Start first lesson
        return await self.deliver_next_lesson(user, session)

    async def deliver_next_lesson(self, user: User, session: Dict) -> str:
        """Deliver next lesson to user"""
        # Get next lesson
        next_lesson = await self.lesson_mgr.get_next_lesson(user.id, user.language.value)

        if not next_lesson:
            # Day complete — record it here (mirrors WhatsApp's
            # handle_day_completion), the single point where every day's
            # completion (1 through 7) is detected
            await self.lesson_mgr.mark_day_complete(user.id, user.current_day)
            session["state"] = USSDMenuState.DAY_COMPLETE
            return await self.show_day_complete(user)

        # Store lesson in session
        session["data"]["current_lesson_id"] = next_lesson.id
        session["data"]["chunk_index"] = 0

        # Chunk the lesson content
        chunks = self.chunker.chunk_text(next_lesson.content)
        session["data"]["lesson_chunks"] = chunks
        session["data"]["lesson_title"] = next_lesson.title

        # Show first chunk
        return await self.show_lesson_chunk(session, 0)

    async def show_lesson_chunk(self, session: Dict, chunk_index: int) -> str:
        """Display a specific lesson chunk"""
        chunks = session["data"].get("lesson_chunks", [])
        title = session["data"].get("lesson_title", "Lesson")

        if chunk_index >= len(chunks):
            chunk_index = len(chunks) - 1

        chunk = chunks[chunk_index]
        total_chunks = len(chunks)

        # Format with header
        header = f"{title}\n{'='*20}\n\n"
        formatted_chunk = self.chunker.format_lesson_chunk(chunk, chunk_index, total_chunks)

        # Combine (may exceed 160, but close enough for USSD)
        return USSDResponse.con(header + formatted_chunk)

    async def handle_lesson_display(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle lesson display navigation"""
        if choice == "0":
            # Return to main menu
            session["state"] = USSDMenuState.MAIN_MENU
            session["data"] = {}
            return await self.show_main_menu()

        elif choice == "1":
            # Continue or take quiz
            chunks = session["data"].get("lesson_chunks", [])
            current_index = session["data"].get("chunk_index", 0)

            if current_index < len(chunks) - 1:
                # Show next chunk
                next_index = current_index + 1
                session["data"]["chunk_index"] = next_index
                return await self.show_lesson_chunk(session, next_index)
            else:
                # Last chunk, start quiz
                session["state"] = USSDMenuState.QUIZ_QUESTION
                session["data"]["quiz_answers"] = []
                session["data"]["current_question"] = 0
                return await self.show_quiz_question(user, session, 0)

        else:
            return USSDResponse.end("Invalid choice. Dial *384*8080# to continue.")

    async def show_quiz_question(self, user: User, session: Dict, question_num: int) -> str:
        """Display quiz question"""
        lesson_id = session["data"].get("current_lesson_id")

        # Get lesson
        result = await self.db.execute(
            select(Lesson).where(Lesson.id == lesson_id)
        )
        lesson = result.scalar_one_or_none()

        if not lesson or question_num >= len(lesson.quiz):
            return USSDResponse.end("Error loading quiz. Please try again.")

        quiz_item = lesson.quiz[question_num]
        question = quiz_item["question"]
        options = quiz_item["options"]

        # Format question
        response = f"Question {question_num + 1}/5\n\n{question}\n\n"
        for i, option in enumerate(options, 1):
            response += f"{i}. {option[:50]}\n"  # Truncate long options

        return USSDResponse.con(response)

    async def handle_quiz_question(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle quiz question response"""
        if choice not in ["1", "2", "3", "4"]:
            return USSDResponse.end("Invalid answer. Dial *384*8080# to retry.")

        # Record answer (convert to 0-indexed)
        answer_index = int(choice) - 1
        session["data"]["quiz_answers"].append(answer_index)

        current_question = session["data"]["current_question"]

        if current_question < 4:
            # More questions
            next_question = current_question + 1
            session["data"]["current_question"] = next_question
            return await self.show_quiz_question(user, session, next_question)
        else:
            # Quiz complete, score it
            lesson_id = session["data"]["current_lesson_id"]
            answers = session["data"]["quiz_answers"]

            result = await self.lesson_mgr.record_quiz_attempt(
                user.id,
                lesson_id,
                answers
            )

            # Store result
            session["data"]["quiz_result"] = {
                "score": result.score,
                "passed": result.passed,
                "attempt": result.attempt_number,
                "can_retry": result.can_retry
            }
            session["state"] = USSDMenuState.QUIZ_RESULT

            return await self.show_quiz_result(session)

    async def show_quiz_result(self, session: Dict) -> str:
        """Display quiz result"""
        result = session["data"].get("quiz_result", {})
        score = result.get("score", 0)
        passed = result.get("passed", False)
        attempt = result.get("attempt", 1)

        if passed:
            response = (
                f"PASSED!\n\n"
                f"Score: {score:.0f}%\n"
                f"Attempt: {attempt}/3\n\n"
                f"Great job! Moving to next lesson...\n\n"
                f"1. Continue\n"
                f"0. Main Menu"
            )
        else:
            can_retry = result.get("can_retry", False)
            response = (
                f"Not quite!\n\n"
                f"Score: {score:.0f}%\n"
                f"Need: 60%\n"
                f"Attempt: {attempt}/3\n\n"
            )
            if can_retry:
                response += "1. Retry Quiz\n"
            response += "0. Main Menu"

        return USSDResponse.con(response)

    async def handle_quiz_result(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle quiz result navigation"""
        if choice == "0":
            session["state"] = USSDMenuState.MAIN_MENU
            session["data"] = {}
            return await self.show_main_menu()

        elif choice == "1":
            result = session["data"].get("quiz_result", {})
            passed = result.get("passed", False)

            if passed:
                # Move to next lesson
                session["state"] = USSDMenuState.LESSON_DISPLAY
                session["data"] = {"chunk_index": 0}
                return await self.deliver_next_lesson(user, session)
            else:
                # Retry quiz
                session["state"] = USSDMenuState.QUIZ_QUESTION
                session["data"]["quiz_answers"] = []
                session["data"]["current_question"] = 0
                return await self.show_quiz_question(user, session, 0)

        else:
            return USSDResponse.end("Invalid choice.")

    async def show_progress(self, user: User) -> str:
        """Display user progress"""
        progress = await self.lesson_mgr.get_user_progress(user.id)

        if not progress:
            return USSDResponse.end("No progress yet. Start learning!")

        response = (
            f"Your Progress\n{'='*20}\n\n"
            f"Current Day: {progress.current_day}/7\n"
            f"Lessons Done: {progress.lessons_completed}/{progress.total_lessons}\n"
            f"Completion: {progress.completion_percentage:.0f}%\n\n"
            f"Keep going! You're doing great!"
        )

        return USSDResponse.end(response)

    async def show_day_complete(self, user: User) -> str:
        """Display day completion message"""
        return USSDResponse.con(
            f"DAY {user.current_day} COMPLETE!\n\n"
            f"Congratulations!\n"
            f"All {user.current_day * 5} lessons done!\n\n"
            f"1. Start Day {user.current_day + 1}\n"
            f"0. Main Menu"
        )

    async def handle_day_complete(
        self,
        user: User,
        session: Dict,
        choice: str
    ) -> str:
        """Handle day completion navigation"""
        if choice == "0":
            session["state"] = USSDMenuState.MAIN_MENU
            session["data"] = {}
            return await self.show_main_menu()

        elif choice == "1":
            # Advance to next day
            advanced = await self.lesson_mgr.advance_to_next_day(user.id)

            if advanced:
                await self.db.refresh(user)
                session["state"] = USSDMenuState.LESSON_DISPLAY
                session["data"] = {"chunk_index": 0}
                return await self.deliver_next_lesson(user, session)
            else:
                return USSDResponse.end("Could not advance. Please try again.")

        else:
            return USSDResponse.end("Invalid choice.")


# FastAPI Router for USSD webhooks
router = APIRouter(prefix="/api/v1/ussd", tags=["ussd"])


@router.post("/callback")
async def ussd_callback(
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Africa's Talking USSD callback endpoint

    Args:
        sessionId: Unique session ID from AT
        serviceCode: USSD code dialed (*384*8080#)
        phoneNumber: User phone number
        text: User input (empty for new session)

    Returns:
        USSD response string (CON or END)
    """
    # Create Redis client
    redis_client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )

    try:
        # Create handler
        handler = USSDHandler(db, redis_client, settings)

        # Handle request
        response = await handler.handle_request(sessionId, phoneNumber, text)

        return response

    finally:
        await redis_client.close()
