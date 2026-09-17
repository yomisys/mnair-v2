"""
Telegram channel for MNAIR — the free replacement for WhatsApp.

Why Telegram: the Bot API is free with no per-message billing, no template
approval and no 24-hour reply window, and it supports inline buttons that
map 1:1 onto the buttons the engine already emits. Nothing here touches the
curriculum flow; that lives in app.engine.conversation.

Two ways to receive updates, both feeding process_update():

  * Webhook  — POST /api/v1/webhooks/telegram (production; needs a public
               HTTPS URL; register with `python telegram_bot.py --set-webhook`)
  * Polling  — `python telegram_bot.py` long-polls getUpdates (dev, or any
               deployment without a public URL)

Identity: learners are keyed as "tg:{chat_id}" in User.phone_number (see
app.engine.identity) and the chat id is also stored in User.telegram_chat_id
for outbound reminders.
"""

import html
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.engine import ConversationEngine, get_or_create_conversation, get_or_create_learner
from app.engine.identity import telegram_identity
from app.engine.messages import Button, OutboundMessage
from app.middleware.rate_limit import limiter, WEBHOOK_RATE_LIMIT
from app.models.conversation import ConversationChannel

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_BUTTON_LIMIT = 40  # visual, not API — longer labels wrap badly on phones

# Slash commands -> engine keywords. /start doubles as CONTINUE for returning
# learners; a brand-new conversation ignores the text anyway.
SLASH_COMMANDS = {
    "/start": "CONTINUE",
    "/continue": "CONTINUE",
    "/quiz": "QUIZ",
    "/next": "NEXT",
    "/language": "LANGUAGE",
    "/certificate": "CERTIFICATE",
    "/progress": "PROGRESS",
    "/help": "HELP",
}

HELP_TEXT = (
    "🤖 *MNAIR commands*\n\n"
    "/continue — pick up where you stopped\n"
    "/quiz — start the quiz for your current lesson\n"
    "/next — move to the next day\n"
    "/language — change your learning language\n"
    "/progress — see how far you've come\n"
    "/certificate — get your certificate (after Day 7)\n\n"
    "You can also just tap the buttons under each message."
)


# ---------------------------------------------------------------------------
# Rendering: OutboundMessage -> Telegram sendMessage payload
# ---------------------------------------------------------------------------

_BOLD = re.compile(r"\*(.+?)\*")


def render_html(text: str) -> str:
    """Convert the engine's *bold* markup to Telegram HTML, escaping the rest.

    HTML parse mode is used instead of Markdown because Telegram's Markdown
    treats '_' and '*' inside ordinary words as formatting and rejects the
    message — curriculum text (topic ids like what_is_ai, maths like 2*3)
    would trip it. Escaping first and only then inserting <b> tags is safe.
    """
    escaped = html.escape(text, quote=False)
    return _BOLD.sub(r"<b>\1</b>", escaped)


def chunk_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Split on paragraph boundaries so no chunk exceeds Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > limit and current:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    # A single paragraph longer than the limit is hard-split as a last resort
    out: List[str] = []
    for c in chunks:
        while len(c) > limit:
            out.append(c[:limit])
            c = c[limit:]
        out.append(c)
    return out


def build_keyboard(buttons: List[Button]) -> Optional[Dict[str, Any]]:
    """Inline keyboard: quiz answers 2-per-row, everything else 1-per-row.
    A button whose description is a URL becomes a link button."""
    if not buttons:
        return None
    rows: List[List[Dict[str, str]]] = []
    answer_buttons = [b for b in buttons if b.id.startswith("ans_")]
    other_buttons = [b for b in buttons if not b.id.startswith("ans_")]

    for i in range(0, len(answer_buttons), 2):
        rows.append([_button_dict(b) for b in answer_buttons[i:i + 2]])
    for b in other_buttons:
        rows.append([_button_dict(b)])
    return {"inline_keyboard": rows}


def _button_dict(b: Button) -> Dict[str, str]:
    title = b.title if len(b.title) <= TELEGRAM_BUTTON_LIMIT else b.title[:TELEGRAM_BUTTON_LIMIT - 1] + "…"
    if b.description.startswith("http://") or b.description.startswith("https://"):
        return {"text": title, "url": b.description}
    return {"text": title, "callback_data": b.id[:64]}


def to_send_payloads(chat_id: int, message: OutboundMessage) -> List[Dict[str, Any]]:
    """One OutboundMessage may become several sendMessage calls if it is
    over the text limit; the keyboard is attached to the last one."""
    chunks = chunk_text(message.text)
    payloads: List[Dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": render_html(chunk),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if i == len(chunks) - 1:
            kb = build_keyboard(message.buttons)
            if kb:
                payload["reply_markup"] = kb
        payloads.append(payload)
    return payloads


# ---------------------------------------------------------------------------
# Bot API client
# ---------------------------------------------------------------------------

class TelegramClient:
    """Thin async wrapper over the Bot API. No token = dev mode (log only)."""

    def __init__(self, settings: Settings, http: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self.token = settings.TELEGRAM_BOT_TOKEN
        self._http = http

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API}/bot{self.token}/{method}"

    async def call(self, method: str, payload: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            logger.info("[DEV MODE] Telegram %s: %s", method, payload)
            return {"ok": True, "result": payload}
        client = self._http or httpx.AsyncClient()
        try:
            response = await client.post(self._url(method), json=payload, timeout=timeout)
            data = response.json()
            if not data.get("ok"):
                logger.error("Telegram %s failed: %s", method, data.get("description"))
                return None
            return data
        except (httpx.HTTPError, ValueError) as e:
            logger.error("Telegram %s error: %s", method, e)
            return None
        finally:
            if self._http is None:
                await client.aclose()

    async def send_message(self, chat_id: int, message: OutboundMessage) -> bool:
        ok = True
        for payload in to_send_payloads(chat_id, message):
            if await self.call("sendMessage", payload) is None:
                ok = False
        return ok

    async def send_text(self, chat_id: int, text: str) -> bool:
        return await self.send_message(chat_id, OutboundMessage.text_only(text))

    async def answer_callback_query(self, callback_query_id: str) -> None:
        await self.call("answerCallbackQuery", {"callback_query_id": callback_query_id}, timeout=5.0)

    async def set_webhook(self, url: str) -> bool:
        payload: Dict[str, Any] = {
            "url": url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        if self.settings.TELEGRAM_WEBHOOK_SECRET:
            payload["secret_token"] = self.settings.TELEGRAM_WEBHOOK_SECRET
        return (await self.call("setWebhook", payload)) is not None

    async def delete_webhook(self) -> bool:
        return (await self.call("deleteWebhook", {"drop_pending_updates": False})) is not None

    async def set_my_commands(self) -> bool:
        commands = [
            {"command": "continue", "description": "Pick up where you stopped"},
            {"command": "quiz", "description": "Start the quiz for this lesson"},
            {"command": "next", "description": "Move to the next day"},
            {"command": "language", "description": "Change learning language"},
            {"command": "progress", "description": "See your progress"},
            {"command": "certificate", "description": "Get your certificate"},
            {"command": "help", "description": "Show commands"},
        ]
        return (await self.call("setMyCommands", {"commands": commands})) is not None

    async def get_updates(self, offset: Optional[int], timeout: int) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        data = await self.call("getUpdates", payload, timeout=timeout + 10)
        if not data:
            return []
        return data.get("result", []) if isinstance(data.get("result"), list) else []


# ---------------------------------------------------------------------------
# Update processing
# ---------------------------------------------------------------------------

def parse_update(update: Dict[str, Any]) -> Optional[Tuple[int, str, Optional[str], Optional[str], Optional[str]]]:
    """Extract (chat_id, text, interactive_id, callback_query_id, first_name)
    from a Telegram update, or None if it is nothing we handle."""
    if "callback_query" in update:
        cq = update["callback_query"]
        message = cq.get("message") or {}
        chat = message.get("chat") or {}
        if "id" not in chat:
            return None
        sender = cq.get("from") or {}
        return int(chat["id"]), "", cq.get("data"), cq.get("id"), sender.get("first_name")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return None
    chat = message.get("chat") or {}
    if "id" not in chat or chat.get("type") not in (None, "private"):
        return None  # groups/channels are not learner conversations
    sender = message.get("from") or {}
    text = message.get("text") or message.get("caption") or ""
    return int(chat["id"]), text, None, None, sender.get("first_name")


class TelegramChannel:
    """Glue between Telegram updates and the ConversationEngine."""

    def __init__(self, db: AsyncSession, settings: Settings, client: Optional[TelegramClient] = None):
        self.db = db
        self.settings = settings
        self.client = client or TelegramClient(settings)
        self.engine = ConversationEngine(db, settings)

    async def process_update(self, update: Dict[str, Any]) -> List[OutboundMessage]:
        parsed = parse_update(update)
        if not parsed:
            return []
        chat_id, text, interactive_id, callback_query_id, first_name = parsed

        if callback_query_id:
            # Stop the button's loading spinner immediately; the reply follows
            await self.client.answer_callback_query(callback_query_id)

        # Slash commands (with optional @botname suffix and /start payload)
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else None
        if command == "/help":
            await self.client.send_message(chat_id, OutboundMessage.text_only(HELP_TEXT))
            return []
        if command in SLASH_COMMANDS:
            text = SLASH_COMMANDS[command]

        user = await get_or_create_learner(
            self.db,
            identity=telegram_identity(chat_id),
            channel=ConversationChannel.TELEGRAM,
            telegram_chat_id=str(chat_id),
        )
        conversation = await get_or_create_conversation(self.db, user, ConversationChannel.TELEGRAM)
        conversation.external_id = str(update.get("update_id", conversation.external_id or ""))

        replies = await self.engine.handle(user, conversation, text, interactive_id)
        for reply in replies:
            await self.client.send_message(chat_id, reply)
        return replies


# ---------------------------------------------------------------------------
# Webhook route
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/telegram")
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Receive one Telegram update. Always returns 200 quickly — Telegram
    retries anything else, which would replay learner input."""
    if settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    elif settings.APP_ENV == "production":
        raise HTTPException(status_code=503, detail="TELEGRAM_WEBHOOK_SECRET not configured")

    try:
        update = await request.json()
    except ValueError:
        return {"status": "ignored"}

    channel = TelegramChannel(db, settings)
    try:
        await channel.process_update(update)
    except Exception as e:  # noqa: BLE001 — never let one bad update 5xx the webhook
        logger.exception("Telegram update %s failed: %s", update.get("update_id"), e)
    return {"status": "ok"}
