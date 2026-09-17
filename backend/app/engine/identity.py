"""
Learner identity resolution shared by every free channel.

Identity slot: User.phone_number is the unique learner key. Channels with a
real phone number (web enrolment, USSD, SMS) store the normalised +234
number. Channels without one store a prefixed external id in the same slot,
exactly like the existing KingsChat pattern ("kc:{id}"):

    Telegram  ->  "tg:{chat_id}"

The column is 64 chars wide, which comfortably fits both.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Language, UserRole
from app.models.conversation import Conversation, ConversationChannel, ConversationState


TELEGRAM_IDENTITY_PREFIX = "tg:"


def telegram_identity(chat_id: int) -> str:
    return f"{TELEGRAM_IDENTITY_PREFIX}{chat_id}"


async def get_or_create_learner(
    db: AsyncSession,
    identity: str,
    channel: ConversationChannel,
    name: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> User:
    """Look up a learner by identity slot, creating them on first contact."""
    result = await db.execute(select(User).where(User.phone_number == identity))
    user = result.scalar_one_or_none()

    if not user:
        placeholder = {
            ConversationChannel.TELEGRAM: "Telegram User",
            ConversationChannel.WEB: "Web Learner",
        }.get(channel, "Learner")
        user = User(
            phone_number=identity,
            name=name or placeholder,
            language=Language.ENGLISH,  # default; the flow asks on first contact
            role=UserRole.LEARNER,
            current_day=1,
            preferred_channel=channel.value,
            telegram_chat_id=telegram_chat_id,
            consent_given=True,  # implied by starting the course; web enrolment asks explicitly
            consent_date=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif telegram_chat_id and not user.telegram_chat_id:
        user.telegram_chat_id = telegram_chat_id
        await db.commit()

    return user


async def get_or_create_conversation(
    db: AsyncSession,
    user: User,
    channel: ConversationChannel,
) -> Conversation:
    """Active conversation for this user on this channel, or a fresh NEW_USER one."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.channel == channel,
            Conversation.is_active == True,  # noqa: E712
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            channel=channel,
            phone_number=user.phone_number,
            current_state=ConversationState.NEW_USER,
            is_active=True,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    return conversation
