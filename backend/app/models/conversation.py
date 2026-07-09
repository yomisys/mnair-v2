from __future__ import annotations

"""
Conversation model - Tracks WhatsApp/USSD session state
Manages conversation flow, state machine, and message history
"""

from datetime import datetime
from enum import Enum
from typing import List,Optional
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ConversationState(str, Enum):
    """Conversation states for state machine"""
    NEW_USER = "new_user"
    AWAITING_NAME = "awaiting_name"
    AWAITING_LANGUAGE = "awaiting_language"
    AWAITING_CONSENT = "awaiting_consent"
    IN_LESSON = "in_lesson"
    AWAITING_QUIZ = "awaiting_quiz"
    DAY_COMPLETE = "day_complete"
    AWAITING_CERTIFICATE_NAME = "awaiting_certificate_name"
    PROGRAM_COMPLETE = "program_complete"
    IDLE = "idle"


class ConversationChannel(str, Enum):
    """Communication channels"""
    WHATSAPP = "whatsapp"
    USSD = "ussd"
    SMS = "sms"


class Conversation(Base):
    """
    Conversation state tracker for multi-channel communication
    Manages WhatsApp, USSD, SMS sessions
    """
    __tablename__ = "conversations"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign Key
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Channel Information
    channel: Mapped[ConversationChannel] = mapped_column(
        SQLEnum(ConversationChannel),
        nullable=False,
        index=True,
        comment="Communication channel: whatsapp, ussd, sms"
    )

    # External IDs (for channel-specific tracking)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        index=True,
        comment="WhatsApp message ID, USSD session ID, etc."
    )

    phone_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        index=True,
        comment="User's phone number for this conversation"
    )

    # State Management
    current_state: Mapped[ConversationState] = mapped_column(
        SQLEnum(ConversationState),
        default=ConversationState.NEW_USER,
        nullable=False,
        index=True,
        comment="Current conversation state"
    )

    previous_state: Mapped[Optional[ConversationState]] = mapped_column(
        SQLEnum(ConversationState),
        comment="Previous state (for back navigation)"
    )

    # Context Data (stored as JSON)
    context: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="""
        Conversation context data:
        {
            "current_lesson_id": 123,
            "current_question_index": 2,
            "quiz_answers": [0, 2, 1],
            "awaiting_input": "quiz_answer",
            "retry_count": 0
        }
        """
    )

    # Current Lesson Tracking
    current_lesson_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL"),
        index=True,
        comment="Current lesson being delivered"
    )

    # Message History (last N messages for context)
    message_history: Mapped[list] = mapped_column(
        JSON,
        default=list,
        comment="""
        Last 10 messages:
        [
            {"role": "user", "content": "Hi", "timestamp": "..."},
            {"role": "bot", "content": "Welcome!", "timestamp": "..."}
        ]
        """
    )

    # Session Management
    is_active: Mapped[bool] = mapped_column(
        default=True,
        comment="Session is currently active"
    )

    session_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    session_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="When session ended (timeout or completion)"
    )

    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Last message timestamp (for timeout detection)"
    )

    # USSD-specific (90-second timeout)
    ussd_session_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        index=True,
        comment="Africa's Talking USSD session ID"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="conversations")

    # Indexes
    __table_args__ = (
        Index("idx_conv_user_channel", "user_id", "channel"),
        Index("idx_conv_state_active", "current_state", "is_active"),
        Index("idx_conv_phone", "phone_number"),
        Index("idx_conv_ussd_session", "ussd_session_id"),
    )

    def __repr__(self) -> str:
        return f"<Conversation user={self.user_id} channel={self.channel.value} state={self.current_state.value}>"

    def transition_to(self, new_state: ConversationState) -> None:
        """Transition to a new state"""
        self.previous_state = self.current_state
        self.current_state = new_state
        self.updated_at = datetime.utcnow()

    def add_message(self, role: str, content: str, max_history: int = 10) -> None:
        """
        Add message to conversation history
        Keep only last N messages
        """
        if not isinstance(self.message_history, list):
            self.message_history = []

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.message_history.append(message)

        # Keep only last N messages
        if len(self.message_history) > max_history:
            self.message_history = self.message_history[-max_history:]

        self.last_message_at = datetime.utcnow()

    def update_context(self, key: str, value: any) -> None:
        """Update conversation context"""
        if not isinstance(self.context, dict):
            self.context = {}

        self.context[key] = value
        self.updated_at = datetime.utcnow()

    def get_context(self, key: str, default: any = None) -> any:
        """Get value from conversation context"""
        if not isinstance(self.context, dict):
            return default

        return self.context.get(key, default)

    def is_timed_out(self, timeout_seconds: int = 300) -> bool:
        """
        Check if conversation has timed out
        Default: 5 minutes for WhatsApp, 90 seconds for USSD
        """
        if not self.last_message_at:
            return False

        elapsed = (datetime.utcnow() - self.last_message_at).total_seconds()
        return elapsed > timeout_seconds

    def end_session(self) -> None:
        """End the conversation session"""
        self.is_active = False
        self.session_ended_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    @property
    def is_whatsapp(self) -> bool:
        """Check if conversation is via WhatsApp"""
        return self.channel == ConversationChannel.WHATSAPP

    @property
    def is_ussd(self) -> bool:
        """Check if conversation is via USSD"""
        return self.channel == ConversationChannel.USSD

    @property
    def is_sms(self) -> bool:
        """Check if conversation is via SMS"""
        return self.channel == ConversationChannel.SMS

    @property
    def session_duration_seconds(self) -> Optional[int]:
        """Get session duration in seconds"""
        if not self.session_started_at:
            return None

        end_time = self.session_ended_at or datetime.utcnow()
        return int((end_time - self.session_started_at).total_seconds())
