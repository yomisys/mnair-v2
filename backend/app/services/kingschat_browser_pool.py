"""
KingsChat browser context pool.

Architecture decision from /plan-eng-review (2026-07-12): one shared
Playwright browser process, many pooled BrowserContexts, reused via a
pool — not one full browser process per learner.

RESOLVED (was TODOS.md P0 "verify fingerprint isolation before pooling"):
the premise behind that item doesn't apply to this architecture. Every
context this pool creates carries the SAME storage_state (see
set_storage_state / _context_options) -- there is one automated KingsChat
account (Open Question 1, resolved to a single shared bot account), not
one account per learner. Pooling here exists purely to parallelize page
operations (navigating conversations, sending messages) under that one
already-known identity; it is not trying to make N contexts look like N
different unlinked people. Cross-context fingerprint correlation (IP, TLS,
canvas/WebGL -- confirmed via research to NOT be isolated by BrowserContext
even when contexts don't share storage_state) is therefore moot here: pool
size does not add any distinguishing signal beyond what a single context
under this account already exposes. KINGSCHAT_CONTEXT_PROXY_SERVER is kept
as a no-cost escape hatch (e.g. if a future multi-account model is ever
adopted) but is not required by anything in the current single-account
design.

The risk that DOES apply, independent of pool_size, is standard
single-account headless-automation detection: navigator.webdriver=true,
HeadlessChrome-flavored signatures, a SwiftShader/software WebGL renderer,
and behavioral tells (no mouse movement, inhuman action cadence). See
`start()`/`acquire()` below for the mitigations applied against that --
these are standard hardening for any production Playwright deployment
driving a real account on a real site, not ToS-circumvention tooling.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

logger = logging.getLogger(__name__)


class PoolExhaustedTimeout(Exception):
    """Raised when a caller waits longer than the configured timeout for a
    context to become available. Distinct from a plain queue wait so
    callers can decide whether to retry, queue the learner's message for
    later, or surface a "please wait" response."""


class KingsChatBrowserPool:
    """Bounded pool of Playwright BrowserContexts sharing one Browser.

    Usage:
        pool = KingsChatBrowserPool(pool_size=10, storage_state=..., proxy_server=...)
        await pool.start()
        async with pool.acquire() as context:
            page = await context.new_page()
            ...
        await pool.stop()
    """

    def __init__(
        self,
        pool_size: int,
        storage_state: Optional[dict] = None,
        proxy_server: Optional[str] = None,
        acquire_timeout_seconds: float = 30.0,
    ):
        if pool_size < 1:
            raise ValueError("pool_size must be >= 1")
        self._pool_size = pool_size
        self._storage_state = storage_state
        self._proxy_server = proxy_server
        self._acquire_timeout_seconds = acquire_timeout_seconds

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._semaphore = asyncio.Semaphore(pool_size)
        self._in_use = 0
        self._waiting = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        # headless=True in production; a real deploy should still be able to
        # flip this via an env var for debugging a broken selector locally.
        # --disable-blink-features=AutomationControlled removes the most
        # commonly checked headless-Chromium tell (it's what flips
        # navigator.webdriver and a few related automation markers in
        # stock headless Chrome) -- standard hardening for any production
        # Playwright deployment driving a real, credentialed account
        # against a real site, independent of the pool-size question above.
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

    def set_storage_state(self, storage_state: dict) -> None:
        """Set (or replace) the storage_state new contexts are created
        with. Needed because login happens after pool construction (the
        pool itself is used to acquire the context that performs the
        login) — see kingschat_bot.py's ensure_logged_in()."""
        self._storage_state = storage_state

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    def _context_options(self) -> dict:
        options: dict = {}
        if self._storage_state is not None:
            options["storage_state"] = self._storage_state
        if self._proxy_server:
            options["proxy"] = {"server": self._proxy_server}
        return options

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BrowserContext]:
        """Acquire an isolated BrowserContext, waiting if the pool is at
        capacity. Logs queue depth and wait time on exhaustion so capacity
        problems are visible in production, not just inferred from learner
        complaints about slow responses (the whole point of making pool
        size a config value instead of a hardcoded guess).
        """
        if self._browser is None:
            raise RuntimeError("KingsChatBrowserPool.start() was not called")

        was_exhausted = self._semaphore.locked()
        wait_start = time.monotonic()
        if was_exhausted:
            async with self._lock:
                self._waiting += 1
            logger.warning(
                "kingschat_pool_exhausted queue_depth=%d pool_size=%d",
                self._waiting, self._pool_size,
            )

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self._acquire_timeout_seconds
            )
        except asyncio.TimeoutError as e:
            if was_exhausted:
                async with self._lock:
                    self._waiting -= 1
            raise PoolExhaustedTimeout(
                f"No BrowserContext available after "
                f"{self._acquire_timeout_seconds}s (pool_size={self._pool_size})"
            ) from e

        if was_exhausted:
            wait_time_ms = (time.monotonic() - wait_start) * 1000
            async with self._lock:
                self._waiting -= 1
            logger.warning(
                "kingschat_pool_wait_resolved wait_time_ms=%.0f", wait_time_ms
            )

        async with self._lock:
            self._in_use += 1

        context = await self._browser.new_context(**self._context_options())
        # Belt-and-suspenders alongside the launch arg in start(): patches
        # navigator.webdriver on every page this context ever opens, in case
        # a future Playwright/Chromium version re-adds a JS-visible signal
        # the launch flag no longer suppresses. Runs before any page script,
        # including KingsChat's own, per add_init_script's contract.
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        try:
            yield context
        finally:
            await context.close()
            async with self._lock:
                self._in_use -= 1
            self._semaphore.release()

    @property
    def in_use(self) -> int:
        return self._in_use

    @property
    def waiting(self) -> int:
        return self._waiting
