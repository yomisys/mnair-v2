"""
Telegram bot runner — long-polling mode (no public URL needed).

    python telegram_bot.py                 # poll forever
    python telegram_bot.py --once          # drain pending updates and exit
    python telegram_bot.py --set-webhook https://api.mnair.ng/api/v1/webhooks/telegram
    python telegram_bot.py --delete-webhook

Polling and webhook are mutually exclusive on Telegram's side: setting a
webhook makes getUpdates return 409, so --set-webhook is for production
(the API process receives updates) and plain polling is for development or
a single-box deployment. Both paths call the same TelegramChannel.
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.channels.telegram import TelegramChannel, TelegramClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("telegram_bot")


async def poll(once: bool) -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set — nothing to poll. Add it to .env.")
        return

    client = TelegramClient(settings)
    await client.delete_webhook()  # polling needs no webhook registered
    await client.set_my_commands()
    logger.info("Polling Telegram as @%s (timeout %ss)…", settings.TELEGRAM_BOT_USERNAME or "?", settings.TELEGRAM_POLL_TIMEOUT)

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    offset = None
    while not stop.is_set():
        updates = await client.get_updates(offset, settings.TELEGRAM_POLL_TIMEOUT if not once else 0)
        for update in updates:
            offset = update["update_id"] + 1
            # One DB session per update so a failure never poisons the loop
            async with AsyncSessionLocal() as db:
                channel = TelegramChannel(db, settings, client=client)
                try:
                    await channel.process_update(update)
                except Exception as e:  # noqa: BLE001
                    logger.exception("update %s failed: %s", update.get("update_id"), e)
        if once:
            logger.info("Drained %d update(s).", len(updates))
            return
        if not updates:
            await asyncio.sleep(0.5)


async def set_webhook(url: str) -> int:
    client = TelegramClient(settings)
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        logger.warning("TELEGRAM_WEBHOOK_SECRET is empty — the webhook will accept unsigned requests. Set it in production.")
    ok = await client.set_webhook(url)
    ok = ok and await client.set_my_commands()
    logger.info("setWebhook(%s): %s", url, "ok" if ok else "FAILED")
    return 0 if ok else 1


async def delete_webhook() -> int:
    ok = await TelegramClient(settings).delete_webhook()
    logger.info("deleteWebhook: %s", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="process pending updates then exit")
    parser.add_argument("--set-webhook", metavar="URL", help="register a webhook URL and exit")
    parser.add_argument("--delete-webhook", action="store_true", help="remove the webhook and exit")
    args = parser.parse_args()

    if args.set_webhook:
        return asyncio.run(set_webhook(args.set_webhook))
    if args.delete_webhook:
        return asyncio.run(delete_webhook())
    asyncio.run(poll(args.once))
    return 0


if __name__ == "__main__":
    sys.exit(main())
