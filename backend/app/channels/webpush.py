"""
Web Push notifier — free reminders for web-app learners.

Uses the standard Web Push protocol (VAPID) via `pywebpush`. There is no
provider bill: the browser vendor's push service delivers the notification.
Learners opt in from the learner app; each browser/device becomes one
PushSubscription row. Endpoints that the push service reports as gone
(404/410) are deleted so we stop retrying them.

The pywebpush import is lazy so the API can boot (and tests can run) without
the optional dependency installed; sends are then skipped with a warning.
"""

from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.push_subscription import PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)


def generate_vapid_keys() -> Dict[str, str]:
    """One-off helper: prints a VAPID key pair for .env.

    Uses `cryptography` (already a dependency via python-jose) so it works
    even before pywebpush is installed.
    """
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return {"VAPID_PUBLIC_KEY": b64(public_raw), "VAPID_PRIVATE_KEY": b64(private_raw)}


class WebPushNotifier:
    """Sends a small JSON payload {title, body, url} to every subscription a
    learner has. Returns True if at least one device accepted it."""

    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.webpush_configured

    async def subscriptions_for(self, user: User) -> List[PushSubscription]:
        result = await self.db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id)
        )
        return list(result.scalars().all())

    async def send_to_user(self, user: User, title: str, body: str, url: Optional[str] = None) -> bool:
        subs = await self.subscriptions_for(user)
        if not subs:
            return False
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url or self.settings.learn_url,
        })
        delivered = 0
        for sub in subs:
            status = await self._send_one(sub, payload)
            if status == "sent":
                delivered += 1
                sub.last_used_at = datetime.utcnow()
            elif status == "gone":
                await self.db.delete(sub)
        await self.db.commit()
        return delivered > 0

    async def _send_one(self, sub: PushSubscription, payload: str) -> str:
        """Returns 'sent', 'gone' (endpoint expired) or 'failed'."""
        if not self.enabled:
            logger.info("[DEV MODE] Web push to user %s: %s", sub.user_id, payload)
            return "sent"
        try:
            from pywebpush import webpush, WebPushException  # lazy: optional dependency
        except ImportError:
            logger.warning("pywebpush not installed — web push skipped")
            return "failed"

        def _do_send() -> str:
            try:
                webpush(
                    subscription_info=sub.as_webpush_dict(),
                    data=payload,
                    vapid_private_key=self.settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": self.settings.VAPID_CLAIMS_EMAIL},
                    ttl=60 * 60 * 24,
                )
                return "sent"
            except WebPushException as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code in (404, 410):
                    return "gone"
                logger.error("Web push failed for user %s: %s", sub.user_id, e)
                return "failed"

        # pywebpush is synchronous (requests); keep the event loop free
        return await asyncio.get_event_loop().run_in_executor(None, _do_send)


def parse_browser_subscription(data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Validate a PushSubscription.toJSON() body from the browser."""
    endpoint = data.get("endpoint")
    keys = data.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://") and p256dh and auth):
        return None
    if len(endpoint) > 2048:
        return None
    return {"endpoint": endpoint, "p256dh": str(p256dh)[:255], "auth": str(auth)[:255]}
