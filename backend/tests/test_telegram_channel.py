"""
Telegram channel tests: rendering, keyboards, update parsing, the webhook
route, and a full turn through TelegramChannel with a captured client.
"""

import pytest
from sqlalchemy import select

from app.channels import telegram as tg
from app.config import Settings
from app.engine.messages import Button, OutboundMessage
from app.models.conversation import Conversation, ConversationChannel, ConversationState
from app.models.user import User
from tests.test_engine_flow import seed_days


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def test_render_html_bold_and_escape():
    assert tg.render_html("*Hello* <world> & 2*3") == "<b>Hello</b> &lt;world&gt; &amp; 2*3"
    # underscores in ordinary words must survive (Markdown would reject them)
    assert tg.render_html("topic what_is_ai") == "topic what_is_ai"


def test_chunk_text_splits_on_paragraphs():
    text = "\n\n".join(["para " * 50] * 40)  # ~10k chars
    chunks = tg.chunk_text(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(c.replace("\n\n", "") for c in chunks).replace(" ", "") == text.replace("\n\n", "").replace(" ", "")


def test_keyboard_layout_and_link_buttons():
    msg = OutboundMessage(
        text="q",
        buttons=[Button("ans_0_0", "A", "x"), Button("ans_0_1", "B", "y"), Button("ans_0_2", "C", "z"),
                 Button("ans_0_3", "D", "w"), Button("open_certificate", "Open", "https://mnair.ng/verify?code=1")],
    )
    kb = tg.build_keyboard(msg.buttons)
    assert len(kb["inline_keyboard"]) == 3  # 2 rows of answers + 1 link row
    assert kb["inline_keyboard"][0] == [{"text": "A", "callback_data": "ans_0_0"}, {"text": "B", "callback_data": "ans_0_1"}]
    assert kb["inline_keyboard"][2] == [{"text": "Open", "url": "https://mnair.ng/verify?code=1"}]
    assert tg.build_keyboard([]) is None


def test_send_payload_attaches_keyboard_to_last_chunk():
    msg = OutboundMessage(text="a" * 5000, buttons=[Button("quiz", "Start")])
    payloads = tg.to_send_payloads(7, msg)
    assert len(payloads) == 2
    assert "reply_markup" not in payloads[0]
    assert payloads[1]["reply_markup"]["inline_keyboard"] == [[{"text": "Start", "callback_data": "quiz"}]]
    assert payloads[0]["parse_mode"] == "HTML"


# ---------------------------------------------------------------------------
# update parsing
# ---------------------------------------------------------------------------

def test_parse_update_text_and_callback():
    text_update = {"update_id": 1, "message": {"chat": {"id": 55, "type": "private"}, "from": {"first_name": "Ngozi"}, "text": "hello"}}
    assert tg.parse_update(text_update) == (55, "hello", None, None, "Ngozi")

    cb_update = {"update_id": 2, "callback_query": {"id": "cbq1", "data": "lang_yo", "from": {"first_name": "Ngozi"},
                                                    "message": {"chat": {"id": 55}}}}
    assert tg.parse_update(cb_update) == (55, "", "lang_yo", "cbq1", "Ngozi")

    group = {"update_id": 3, "message": {"chat": {"id": -100, "type": "supergroup"}, "text": "hi"}}
    assert tg.parse_update(group) is None
    assert tg.parse_update({"update_id": 4, "my_chat_member": {}}) is None


# ---------------------------------------------------------------------------
# channel turn with a captured client
# ---------------------------------------------------------------------------

class CapturingClient(tg.TelegramClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.sent = []
        self.answered = []

    async def send_message(self, chat_id, message):
        self.sent.append((chat_id, message))
        return True

    async def answer_callback_query(self, callback_query_id):
        self.answered.append(callback_query_id)


@pytest.mark.asyncio
async def test_telegram_turns_drive_the_engine(test_db):
    await seed_days(test_db)
    settings = Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t")
    client = CapturingClient(settings)
    channel = tg.TelegramChannel(test_db, settings, client=client)

    await channel.process_update({"update_id": 10, "message": {"chat": {"id": 900, "type": "private"}, "text": "/start"}})
    assert [m.kind for _, m in client.sent] == ["text", "choice"]
    assert all(chat == 900 for chat, _ in client.sent)

    user = (await test_db.execute(select(User).where(User.phone_number == "tg:900"))).scalar_one()
    assert user.telegram_chat_id == "900"
    assert user.preferred_channel == "telegram"

    client.sent.clear()
    await channel.process_update({"update_id": 11, "callback_query": {"id": "cb1", "data": "lang_en", "message": {"chat": {"id": 900}}}})
    assert client.answered == ["cb1"]
    assert client.sent[0][1].kind == "lesson"

    conv = (await test_db.execute(select(Conversation).where(Conversation.user_id == user.id))).scalar_one()
    assert conv.channel == ConversationChannel.TELEGRAM
    assert conv.current_state == ConversationState.IN_LESSON
    assert conv.external_id == "11"

    client.sent.clear()
    await channel.process_update({"update_id": 12, "message": {"chat": {"id": 900, "type": "private"}, "text": "/quiz@MnairBot"}})
    assert client.sent[0][1].kind == "quiz"

    client.sent.clear()
    await channel.process_update({"update_id": 13, "message": {"chat": {"id": 900, "type": "private"}, "text": "/help"}})
    assert "MNAIR commands" in client.sent[0][1].text
    # /help never touches the conversation
    assert conv.current_state == ConversationState.AWAITING_QUIZ


@pytest.mark.asyncio
async def test_dev_mode_client_logs_instead_of_sending():
    client = tg.TelegramClient(Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t", TELEGRAM_BOT_TOKEN=None))
    assert client.enabled is False
    assert await client.send_message(1, OutboundMessage.text_only("hi")) is True


# ---------------------------------------------------------------------------
# webhook route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(client, monkeypatch):
    from app.config import settings as live
    monkeypatch.setattr(live, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    r = await client.post("/api/v1/webhooks/telegram", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_accepts_update_and_returns_200(client, test_db, monkeypatch):
    from app.config import settings as live
    monkeypatch.setattr(live, "TELEGRAM_WEBHOOK_SECRET", "s3cret")
    sent = []

    async def fake_send(self, chat_id, message):
        sent.append((chat_id, message))
        return True

    monkeypatch.setattr(tg.TelegramClient, "send_message", fake_send)
    await seed_days(test_db)

    r = await client.post(
        "/api/v1/webhooks/telegram",
        json={"update_id": 1, "message": {"chat": {"id": 321, "type": "private"}, "text": "hello"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert [m.kind for _, m in sent] == ["text", "choice"]

    # garbage body is acknowledged, never 5xx (Telegram would retry it)
    r = await client.post("/api/v1/webhooks/telegram", content=b"not json", headers={
        "X-Telegram-Bot-Api-Secret-Token": "s3cret", "Content-Type": "application/json"})
    assert r.status_code == 200
