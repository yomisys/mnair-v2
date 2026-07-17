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
    KingsChatBanDetectedError,
    KingsChatBanFallback,
    KingsChatLoginError,
    KingsChatWatcher,
    _goto_and_settle,
    get_logged_in_username,
    kingschat_login,
)
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.kingschat_browser_pool import KingsChatBrowserPool
from app.services.kingschat_session_store import KingsChatSessionStore, SessionStoreError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kingschat_bot")


async def _verify_session_identity(page, settings) -> bool:
    """Check whose account the current page's session belongs to, against
    KINGSCHAT_EXPECTED_USERNAME. Page must already be on /conversations.

    Added 2026-07-17 after the first live test ran the entire lesson flow
    as the WRONG account: the stored session predated the bot (captured
    during selector verification against the founder's personal account),
    and the validity check below only ever asked "does this session work?",
    never "whose is it?" — so every 'bot' reply went out as the founder.

    Unset KINGSCHAT_EXPECTED_USERNAME = log the identity but don't enforce
    (backwards compatible); any real deployment should set it.
    """
    handle = await get_logged_in_username(page)
    expected = settings.KINGSCHAT_EXPECTED_USERNAME

    if not expected:
        logger.warning(
            "kingschat_session_identity handle=%s -- KINGSCHAT_EXPECTED_USERNAME "
            "is unset, so this is NOT being enforced. Set it to prevent the "
            "bot silently running as the wrong account.", handle,
        )
        return True

    if handle is None:
        logger.error(
            "kingschat_session_identity_unknown -- could not read the logged-in "
            "handle (profile link never rendered); treating as mismatch since "
            "KINGSCHAT_EXPECTED_USERNAME=%s is set.", expected,
        )
        return False

    ok = handle.lower() == expected.lower()
    (logger.info if ok else logger.error)(
        "kingschat_session_identity handle=%s expected=%s match=%s", handle, expected, ok,
    )
    return ok


async def ensure_logged_in(pool: KingsChatBrowserPool, store: KingsChatSessionStore, settings) -> dict:
    """Return a valid storage_state FOR THE EXPECTED ACCOUNT, logging in
    interactively if no stored session exists, the stored one no longer
    works, or the stored one belongs to a different account."""
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
            identity_ok = still_valid and await _verify_session_identity(page, settings)
        if still_valid and identity_ok:
            logger.info("kingschat_stored_session_valid")
            return stored
        if still_valid and not identity_ok:
            # Wrong account's session -- discard it so nothing can ever
            # accidentally fall back to it, then fresh-login below.
            logger.warning("kingschat_stored_session_wrong_account -- discarding and logging in again")
            store.clear()
        else:
            logger.warning("kingschat_stored_session_expired -- logging in again")

    async with pool.acquire() as context:
        page = await context.new_page()
        storage_state = await kingschat_login(page, settings.KINGSCHAT_ACCOUNT_EMAIL, settings.KINGSCHAT_ACCOUNT_PASSWORD)
        # Fresh login must ALSO be the right account -- wrong credentials in
        # .env would otherwise reintroduce the exact bug the stored-session
        # check above just caught.
        await _goto_and_settle(page, "https://kingschat.online/conversations")
        if not await _verify_session_identity(page, settings):
            raise KingsChatLoginError(
                f"Fresh login succeeded but as the WRONG account (expected "
                f"@{settings.KINGSCHAT_EXPECTED_USERNAME}) -- the "
                f"KINGSCHAT_ACCOUNT_EMAIL/PASSWORD credentials belong to a "
                f"different account. Session NOT saved."
            )
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

    # Graceful shutdown: finish the in-flight cycle, then exit — a killed
    # mid-send worker would otherwise leave a learner mid-flow (dedupe +
    # stranded-learner recovery would still self-heal, but cleanly draining
    # is better). SIGTERM is what docker stop sends; not available on
    # Windows event loops, hence the guard.
    shutdown = asyncio.Event()
    try:
        import signal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown.set)
    except (NotImplementedError, ImportError):
        pass

    try:
        try:
            storage_state = await ensure_logged_in(pool, store, settings)
        except KingsChatLoginError:
            logger.exception("kingschat_login_failed")
            return 1

        pool.set_storage_state(storage_state)  # subsequent acquire() calls reuse it

        ban_fallback = KingsChatBanFallback(settings)
        watcher = KingsChatWatcher(
            handler=None,  # poll_cycle builds one handler per worker, each on its own DB session
            ban_fallback=ban_fallback,
            session_factory=AsyncSessionLocal,
            settings=settings,
        )

        cycle = 0
        consecutive_failures = 0
        while not shutdown.is_set():
            cycle += 1
            try:
                processed = await watcher.poll_cycle(
                    pool, live=args.live, contact_filter=args.only_contact,
                )
                consecutive_failures = 0
                logger.info(
                    "kingschat_poll_cycle_complete cycle=%d mode=%s processed=%d",
                    cycle, "LIVE" if args.live else "DRY_RUN", processed,
                )
            except KingsChatBanDetectedError:
                # Could be a real ban OR just session expiry — they look
                # identical from inside a page (redirect to login). The
                # re-login ladder distinguishes them: expiry -> fresh login
                # succeeds -> keep going; ban -> login fails -> notify the
                # leader and stop.
                logger.warning("kingschat_session_invalid_signal -- attempting re-login to distinguish expiry from ban")
                try:
                    store.clear()
                    storage_state = await ensure_logged_in(pool, store, settings)
                    pool.set_storage_state(storage_state)
                    logger.info("kingschat_relogin_succeeded -- session had expired, resuming")
                    consecutive_failures = 0
                except KingsChatLoginError:
                    logger.exception("kingschat_relogin_failed -- treating as ban/lockout, stopping")
                    await ban_fallback.notify_leader(lesson=None, reason="session invalid and re-login failed (ban/lockout)")
                    return 1
            except Exception:
                # A whole-cycle failure (network blip, page crash, DB
                # hiccup) must not kill the bot — log, back off, retry.
                # Backoff grows with consecutive failures so a persistent
                # outage doesn't hammer anything, capped at 10 minutes.
                consecutive_failures += 1
                backoff = min(args.interval * (2 ** consecutive_failures), 600)
                logger.exception(
                    "kingschat_poll_cycle_failed cycle=%d consecutive=%d -- backing off %ds",
                    cycle, consecutive_failures, backoff,
                )
                if not args.loop:
                    return 1
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                continue

            if not args.loop:
                break
            # Interruptible sleep: docker stop doesn't wait out the interval
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=args.interval)
            except asyncio.TimeoutError:
                pass

        if shutdown.is_set():
            logger.info("kingschat_bot_shutdown_requested -- drained cleanly")
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
