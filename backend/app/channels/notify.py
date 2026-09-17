"""
NotificationRouter — one place that decides how an outbound message reaches
a learner, and what it costs.

Order of preference is "free first":

  1. Telegram (Bot API, free)           — learners with a telegram_chat_id
  2. Web Push (VAPID, free)             — learners with a push subscription
  3. SMS (Termii, paid)                 — ONLY if SMS_REMINDERS_ENABLED=true

WhatsApp is gone entirely: from 1 October 2026 Meta bills every
conversation, including replies to user-initiated messages, so there is no
free path left on that channel.

Every attempt is written to ReminderLog by the caller so the admin
dashboard's reminder analytics keep working with the new channel names
("telegram", "webpush", "sms").
"""

from __future__ import annotations
import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.channels.sms import SMSNotifier
from app.channels.telegram import TelegramClient
from app.channels.webpush import WebPushNotifier
from app.engine.builder import MessageBuilder
from app.engine.messages import OutboundMessage
from app.models.user import User, Language

logger = logging.getLogger(__name__)


class NotificationRouter:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        telegram: Optional[TelegramClient] = None,
        webpush: Optional[WebPushNotifier] = None,
        sms: Optional[SMSNotifier] = None,
    ):
        self.db = db
        self.settings = settings
        self.telegram = telegram or TelegramClient(settings)
        self.webpush = webpush or WebPushNotifier(db, settings)
        self.sms = sms or SMSNotifier(db, settings)

    # ------------------------------------------------------------------

    async def _has_push(self, user: User) -> bool:
        return bool(await self.webpush.subscriptions_for(user))

    async def send_reminder(self, user: User, days_left: int) -> Tuple[str, bool]:
        """Inactivity nudge. Returns (channel_used, success). channel_used is
        'none' when the learner has no reachable channel."""
        if user.telegram_chat_id:
            message = MessageBuilder.build_reminder_message(user.language, user.current_day, days_left)
            ok = await self.telegram.send_message(int(user.telegram_chat_id), message)
            return "telegram", ok

        if await self._has_push(user):
            copy = MessageBuilder.REMINDER_COPY.get(user.language, MessageBuilder.REMINDER_COPY[Language.ENGLISH])
            body = copy["body"].format(day=user.current_day, days_left=days_left, plural="s" if days_left != 1 else "")
            ok = await self.webpush.send_to_user(
                user,
                title=f"MNAIR — Day {user.current_day} is waiting",
                body=body.split("\n\n")[0],
                url=self.settings.learn_url,
            )
            return "webpush", ok

        if self.settings.SMS_REMINDERS_ENABLED and _is_real_phone(user.phone_number):
            ok = await self.sms.send_reminder_sms(user, days_inactive=0)
            return "sms", ok

        return "none", False

    async def send_certificate_ready(self, user: User, certificate_id: str) -> Tuple[str, bool]:
        """Certificate-ready notice with the verify/download link."""
        from urllib.parse import quote

        verify_url = f"{self.settings.FRONTEND_URL}/verify?code={certificate_id}&name={quote(user.name)}"

        if user.telegram_chat_id:
            message = MessageBuilder.build_certificate_message(user.name, certificate_id, verify_url)
            ok = await self.telegram.send_message(int(user.telegram_chat_id), message)
            return "telegram", ok

        if await self._has_push(user):
            ok = await self.webpush.send_to_user(
                user,
                title="🎓 Your MNAIR certificate is ready",
                body=f"Code {certificate_id}. Tap to download.",
                url=verify_url,
            )
            return "webpush", ok

        if self.settings.SMS_REMINDERS_ENABLED and _is_real_phone(user.phone_number):
            ok = await self.sms.send_certificate_ready_sms(user, certificate_id)
            return "sms", ok

        return "none", False

    async def send_text(self, user: User, text: str, title: str = "MNAIR") -> Tuple[str, bool]:
        """Generic announcement (free channels only — never SMS)."""
        if user.telegram_chat_id:
            ok = await self.telegram.send_message(int(user.telegram_chat_id), OutboundMessage.text_only(text))
            return "telegram", ok
        if await self._has_push(user):
            ok = await self.webpush.send_to_user(user, title=title, body=text)
            return "webpush", ok
        return "none", False


def _is_real_phone(identity: str) -> bool:
    """Telegram/KingsChat learners have 'tg:'/'kc:' identities, not numbers."""
    return identity.startswith("+") or identity[:1].isdigit()
