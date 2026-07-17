"""
KingsChat bot entrypoint.

Standalone script matching this repo's existing flat-script convention
(add_kingschat_channel.py, init_db.py) rather than a FastAPI startup hook —
this is a long-running polling process (browser automation, no webhook),
which is a fundamentally different lifecycle than the request/response app
in app/main.py. Keeping it separate means a normal `uvicorn app.main:app`
deploy never touches KingsChat at all unless this script is run alongside
it, matching KINGSCHAT_ENABLED being off by default in app/config.py.

*** DEFAULTS TO --dry-run. *** First run against a real account should not
be able to post into a real conversation by accident — pass --live only
once you've confirmed dry-run output looks correct (see kingschat.py's
DryRunKingsChatSession).

Usage:
    python kingschat_bot.py                    # dry run, one poll cycle
    python kingschat_bot.py --loop              # dry run, continuous
    python kingschat_bot.py --live --once       # LIVE, one poll cycle
    python kingschat_bot.py --live --loop --interval 30
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.channels.kingschat import (
    DryRunKingsChatSession,
    KingsChatBanDetectedError,
    KingsChatBanFallback,
    KingsChatHandler,
    KingsChatLoginError,
    KingsChatSession,
    KingsChatWatcher,
    _goto_and_settle,
    kingschat_login,
)
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.kingschat_browser_pool import KingsChatBrowserPool
from app.services.kingschat_session_store import KingsChatSessionStore, SessionStoreError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kingschat_bot")


async def ensure_logged_in(pool: KingsChatBrowserPool, store: KingsChatSessionStore, settings) -> dict:
    """Return a valid storage_state, logging in interactively if no stored
    session exists or the stored one no longer works."""
    try:
        stored = store.load()
    except SessionStoreError:
        logger.exception("kingschat_session_store_corrupted -- forcing fresh login")
        stored = None

    if stored is not None:
        # Bug fixed here: the validity check below only means anything if
        # the context it creates actually carries the stored cookies.
        # Without this set_storage_state call, pool.acquire() was handing
        # out a blank context every time, so the check always saw a
        # logged-out redirect and concluded "expired" regardless of
        # whether the saved session was actually still good -- confirmed
        # live 2026-07-12: two consecutive runs both re-logged-in even
        # though the first run's login had just succeeded and saved.
        pool.set_storage_state(stored)
        async with pool.acquire() as context:
            page = await context.new_page()
            # _goto_and_settle: domcontentloaded (not goto()'s default
            # "load") + a bounded, swallowed networkidle attempt --
            # confirmed live 2026-07-12 that kingschat.online never
            # reaches a clean "load" or "networkidle" state (real-time
            # chat app, persistent WebSocket), so bare waits here hung the
            # full 30s default and crashed this exact check twice during
            # testing, in two different ways.
            await _goto_and_settle(page, "https://kingschat.online/conversations")
            still_valid = "accounts.kingschat.online" not in page.url
        if still_valid:
            logger.info("kingschat_stored_session_valid")
            return stored
        logger.warning("kingschat_stored_session_expired -- logging in again")

    async with pool.acquire() as context:
        page = await context.new_page()
        storage_state = await kingschat_login(page, settings.KINGSCHAT_ACCOUNT_EMAIL, settings.KINGSCHAT_ACCOUNT_PASSWORD)
    store.save(storage_state)
    logger.info("kingschat_login_succeeded_session_saved")
    return storage_state


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.KINGSCHAT_ENABLED:
        logger.error("KINGSCHAT_ENABLED is false -- nothing to do. Set it (and the KINGSCHAT_* credentials) to run this.")
        return 1

    store = KingsChatSessionStore(
        path=settings.KINGSCHAT_SESSION_STORE_PATH,
        encryption_key=settings.KINGSCHAT_SESSION_ENCRYPTION_KEY,
    )

    pool = KingsChatBrowserPool(
        pool_size=settings.KINGSCHAT_POOL_SIZE,
        proxy_server=settings.KINGSCHAT_CONTEXT_PROXY_SERVER,
    )
    await pool.start()

    try:
        try:
            storage_state = await ensure_logged_in(pool, store, settings)
        except KingsChatLoginError:
            logger.exception("kingschat_login_failed")
            return 1

        pool.set_storage_state(storage_state)  # subsequent acquire() calls reuse it

        ban_fallback = KingsChatBanFallback(settings)

        cycle = 0
        while True:
            cycle += 1
            async with AsyncSessionLocal() as db:
                handler = KingsChatHandler(settings=settings, db=db)
                watcher = KingsChatWatcher(handler=handler, ban_fallback=ban_fallback)

                async with pool.acquire() as context:
                    page = await context.new_page()
                    real_session = KingsChatSession(page)
                    session = real_session if args.live else DryRunKingsChatSession(real_session)

                    try:
                        processed = await watcher.poll_once(session, contact_filter=args.only_contact)
                    except KingsChatBanDetectedError:
                        logger.error("kingschat_ban_detected -- stopping. Leader notified via KingsChatBanFallback.")
                        return 1

                    logger.info(
                        "kingschat_poll_cycle_complete cycle=%d mode=%s processed=%d",
                        cycle, "LIVE" if args.live else "DRY_RUN", processed,
                    )
                    if not args.live and isinstance(session, DryRunKingsChatSession) and session.sent_log:
                        for conv_id, text in session.sent_log:
                            logger.info("  would send -> %s: %r", conv_id, text[:200])

            if not args.loop:
                break
            await asyncio.sleep(args.interval)

        return 0
    finally:
        await pool.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Actually send messages. Default is dry-run (logs what would be sent).")
    parser.add_argument("--loop", action="store_true", help="Poll continuously. Default is a single poll cycle.")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between poll cycles when --loop is set. Default 30.")
    parser.add_argument(
        "--only-contact", type=str, default=None, metavar="TEXT",
        help=(
            "Scope this run to unread conversations whose visible inbox text contains TEXT "
            "(case-insensitive), e.g. a display name or handle. Every other unread conversation "
            "is left completely untouched -- not clicked, not marked read. Use this for a safe "
            "first --live test against one known conversation on a real, actively-used inbox, "
            "where other unread DMs from real people may be waiting."
        ),
    )
    args = parser.parse_args()

    if args.live:
        logger.warning("kingschat_bot_starting_LIVE_MODE -- this will send real messages to real conversations")
    else:
        logger.info("kingschat_bot_starting_dry_run -- no messages will actually be sent. Use --live to send for real.")
    if args.only_contact:
        logger.info("kingschat_bot_scoped_to_contact filter=%r -- all other unread conversations will be left untouched", args.only_contact)

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
