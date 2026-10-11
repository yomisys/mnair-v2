"""
Web learner channel — the course in a phone browser, no messaging app at all.

The learner app (frontend /learn) is a chat-style UI that talks to these
endpoints. Every turn goes through the same ConversationEngine as Telegram;
the replies come back in the HTTP response instead of being pushed, so the
channel costs nothing per message. Reminders use Web Push (see webpush.py).

Sign-in: phone number + a PIN chosen at enrolment. The old learner login was
passwordless-by-phone, which meant anyone who knew a number could open that
learner's course. A PIN closes that without needing an SMS OTP (which would
cost money per enrolment).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.engine import ConversationEngine, get_or_create_conversation
from app.middleware.rate_limit import limiter, AUTH_RATE_LIMIT, DEFAULT_RATE_LIMIT
from app.models.conversation import ConversationChannel, ConversationState
from app.models.push_subscription import PushSubscription
from app.models.user import User, UserRole, Language
from app.channels.webpush import parse_browser_subscription
from app.schemas.learn import (
    AuthResponse,
    EnrolRequest,
    LearnConfig,
    LearnerSummary,
    LoginRequest,
    MessageRequest,
    ProgressOut,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
    StateResponse,
    TurnResponse,
)
from app.services.lesson_state import LessonStateManager
from app.services.sponsorship import SponsorCodeError, check_code
from app.utils.auth import create_access_token, get_current_user, get_password_hash, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/learn", tags=["Learn (web)"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _summary(user: User) -> LearnerSummary:
    return LearnerSummary(
        id=user.id,
        name=user.name,
        name_confirmed=bool(user.name_confirmed),
        language=user.language.value if hasattr(user.language, "value") else str(user.language),
        current_day=user.current_day,
        completed_days=user.completed_days or 0,
        preferred_channel=user.preferred_channel,
    )


async def _progress(db: AsyncSession, user: User) -> Optional[ProgressOut]:
    summary = await LessonStateManager(db).get_user_progress(user.id)
    if not summary:
        return None
    return ProgressOut(
        current_day=summary.current_day,
        lessons_completed=summary.lessons_completed,
        total_lessons=summary.total_lessons,
        completion_percentage=summary.completion_percentage,
        current_day_progress=summary.current_day_progress,
        lessons_per_day=summary.lessons_per_day,
    )


def _token(user: User, settings: Settings) -> Dict[str, Any]:
    return {
        "access_token": create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
        ),
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
    }


async def _learner_only(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.LEARNER:
        raise HTTPException(status_code=403, detail="Learner account required")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return user


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

@router.get("/config", response_model=LearnConfig)
async def learn_config(settings: Settings = Depends(get_settings)):
    """What the learner app needs before sign-in: Telegram link, push key."""
    return LearnConfig(
        telegram_link=settings.telegram_link,
        vapid_public_key=settings.VAPID_PUBLIC_KEY,
        pin_min_length=settings.LEARNER_PIN_MIN_LENGTH,
        ussd_code=settings.AFRICASTALKING_USSD_CODE,
    )


@router.post("/enrol", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
async def enrol(
    request: Request,
    body: EnrolRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Create a learner with phone + PIN and return the welcome messages."""
    if len(body.pin) < settings.LEARNER_PIN_MIN_LENGTH:
        raise HTTPException(status_code=422, detail=f"PIN must be at least {settings.LEARNER_PIN_MIN_LENGTH} digits")

    existing = (await db.execute(select(User).where(User.phone_number == body.phone_number))).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This number is already enrolled. Sign in with your PIN instead.",
        )

    # Reject a bad sponsor code before creating the account, so the
    # learner can fix a typo instead of ending up unsponsored
    if body.sponsor_code:
        try:
            await check_code(db, body.sponsor_code)
        except SponsorCodeError as e:
            raise HTTPException(status_code=422, detail=str(e))

    user = User(
        phone_number=body.phone_number,
        name=body.name.strip() if body.name else "Web Learner",
        name_confirmed=bool(body.name and body.name.strip()),
        language=Language.ENGLISH,
        role=UserRole.LEARNER,
        current_day=1,
        preferred_channel=ConversationChannel.WEB.value,
        learner_pin_hash=get_password_hash(body.pin),
        consent_given=True,
        consent_date=datetime.utcnow(),
    )
    user.network_operator = user.detect_network_operator()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    conversation = await get_or_create_conversation(db, user, ConversationChannel.WEB)
    start = f"CODE {body.sponsor_code}" if body.sponsor_code else "START"
    replies = await ConversationEngine(db, settings).handle(user, conversation, start)

    return AuthResponse(
        **_token(user, settings),
        learner=_summary(user),
        messages=[m.to_dict() for m in replies],
        state=conversation.current_state.value,
    )


@router.post("/login", response_model=AuthResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Phone + PIN sign-in. A learner who pre-dates PINs (USSD/SMS) claims
    one on their first web sign-in."""
    user = (await db.execute(select(User).where(User.phone_number == body.phone_number))).scalar_one_or_none()
    if not user or user.role != UserRole.LEARNER:
        # Same message as a wrong PIN so the endpoint can't be used to
        # enumerate which numbers are enrolled.
        raise HTTPException(status_code=401, detail="Phone number or PIN is incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    if user.learner_pin_hash:
        if not verify_password(body.pin, user.learner_pin_hash):
            raise HTTPException(status_code=401, detail="Phone number or PIN is incorrect")
    else:
        if len(body.pin) < settings.LEARNER_PIN_MIN_LENGTH:
            raise HTTPException(status_code=422, detail=f"PIN must be at least {settings.LEARNER_PIN_MIN_LENGTH} digits")
        user.learner_pin_hash = get_password_hash(body.pin)
        if user.preferred_channel in (None, "ussd", "sms", "whatsapp"):
            user.preferred_channel = ConversationChannel.WEB.value

    user.last_active_at = datetime.utcnow()
    await db.commit()

    conversation = await get_or_create_conversation(db, user, ConversationChannel.WEB)
    replies = []
    if conversation.current_state == ConversationState.NEW_USER:
        # First time on the web (e.g. came from USSD): kick off the flow so
        # the thread isn't empty.
        replies = await ConversationEngine(db, settings).handle(user, conversation, "START")

    return AuthResponse(
        **_token(user, settings),
        learner=_summary(user),
        messages=[m.to_dict() for m in replies],
        state=conversation.current_state.value,
    )


# ---------------------------------------------------------------------------
# authenticated learner
# ---------------------------------------------------------------------------

@router.get("/state", response_model=StateResponse)
async def get_state(
    user: User = Depends(_learner_only),
    db: AsyncSession = Depends(get_db),
):
    """Thread history + progress so the app can restore itself after reload."""
    conversation = await get_or_create_conversation(db, user, ConversationChannel.WEB)
    subs = (await db.execute(select(PushSubscription.id).where(PushSubscription.user_id == user.id))).first()
    return StateResponse(
        state=conversation.current_state.value,
        learner=_summary(user),
        history=list(conversation.message_history or []),
        progress=await _progress(db, user),
        push_subscribed=subs is not None,
    )


@router.post("/message", response_model=TurnResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def send_message(
    request: Request,
    body: MessageRequest,
    user: User = Depends(_learner_only),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """One learner turn: typed text and/or a tapped button id."""
    if not body.text and not body.interactive_id:
        raise HTTPException(status_code=422, detail="Send text or a button id")

    conversation = await get_or_create_conversation(db, user, ConversationChannel.WEB)
    replies = await ConversationEngine(db, settings).handle(
        user, conversation, body.text or "", body.interactive_id
    )
    await db.refresh(user)
    return TurnResponse(
        messages=[m.to_dict() for m in replies],
        state=conversation.current_state.value,
        learner=_summary(user),
        progress=await _progress(db, user),
    )


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def push_subscribe(
    body: PushSubscribeRequest,
    user: User = Depends(_learner_only),
    db: AsyncSession = Depends(get_db),
):
    """Store this browser's push subscription (idempotent on endpoint)."""
    parsed = parse_browser_subscription(body.subscription)
    if not parsed:
        raise HTTPException(status_code=422, detail="Invalid push subscription")

    existing = (await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == parsed["endpoint"])
    )).scalar_one_or_none()
    if existing:
        existing.user_id = user.id
        existing.p256dh = parsed["p256dh"]
        existing.auth = parsed["auth"]
        existing.user_agent = body.user_agent
    else:
        db.add(PushSubscription(user_id=user.id, user_agent=body.user_agent, **parsed))
    if user.preferred_channel != ConversationChannel.TELEGRAM.value:
        user.preferred_channel = ConversationChannel.WEB.value
    await db.commit()
    return None


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def push_unsubscribe(
    body: PushUnsubscribeRequest,
    user: User = Depends(_learner_only),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == user.id,
        )
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return None


@router.post("/forget-me", status_code=status.HTTP_204_NO_CONTENT)
async def forget_me(
    user: User = Depends(_learner_only),
    db: AsyncSession = Depends(get_db),
):
    """NDPA erasure: deactivate and scrub the learner's personal data.
    Progress rows cascade-delete with the user."""
    await db.delete(user)
    await db.commit()
    return None
