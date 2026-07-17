"""
KingsChat session store — encrypted-at-rest storage for the captured login
session (cookies/storage state) that Playwright uses to avoid re-logging-in
on every restart.

Why encrypted: this file is functionally a credential. A captured KingsChat
session bypasses the login form and any 2FA entirely — worse than the plain
account password if it leaks, since a password alone still needs a working
login flow to be useful. Locked in during /plan-eng-review on 2026-07-12
after a cross-model review flagged that "required env var, no default" (the
fix for the repo's other credential-exposure P0) doesn't by itself protect
a file that sits on disk in plaintext.

Encryption: Fernet (symmetric, authenticated) from `cryptography`, already a
transitive dependency via python-jose[cryptography]. The key comes from
KINGSCHAT_SESSION_ENCRYPTION_KEY (required whenever KINGSCHAT_ENABLED=true —
see app.config's validator). Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken


class SessionStoreError(Exception):
    """Raised when the session store can't be read or written safely."""


class KingsChatSessionStore:
    """Reads/writes Playwright's `storage_state` JSON, encrypted at rest.

    One store instance per configured path. Not thread-safe for concurrent
    writers to the same path — the browser pool (see
    kingschat_browser_pool.py) only ever has one writer (the login flow), so
    this is intentionally simple rather than adding file-locking machinery
    for a case that doesn't occur.
    """

    def __init__(self, path: str, encryption_key: str):
        self._path = Path(path)
        try:
            self._fernet = Fernet(encryption_key.encode())
        except (ValueError, TypeError) as e:
            raise SessionStoreError(
                "KINGSCHAT_SESSION_ENCRYPTION_KEY is not a valid Fernet key. "
                "Generate one with: python -c \"from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())\""
            ) from e

    def load(self) -> Optional[dict[str, Any]]:
        """Return the decrypted storage_state dict, or None if no session
        has been saved yet (first-run case — the caller should fall through
        to an interactive/first-time login instead of crashing).

        Raises SessionStoreError if the file exists but can't be decrypted
        or parsed — this is a real failure state (wrong key, corrupted
        file, tampering) and must not be silently treated as "no session".
        """
        if not self._path.exists():
            return None

        encrypted = self._path.read_bytes()
        if not encrypted:
            # An empty file is a prior write that was interrupted — treat as
            # corrupted, not as "no session", so it surfaces instead of
            # silently forcing a fresh login every single restart.
            raise SessionStoreError(
                f"Session store at {self._path} exists but is empty — "
                "likely an interrupted write. Delete it to force a fresh "
                "login, or restore from backup."
            )

        try:
            decrypted = self._fernet.decrypt(encrypted)
        except InvalidToken as e:
            raise SessionStoreError(
                f"Session store at {self._path} could not be decrypted — "
                "wrong KINGSCHAT_SESSION_ENCRYPTION_KEY, or the file is "
                "corrupted/tampered. Not falling back to a fresh login "
                "automatically: that would silently mask a real problem."
            ) from e

        try:
            return json.loads(decrypted)
        except json.JSONDecodeError as e:
            raise SessionStoreError(
                f"Session store at {self._path} decrypted but is not valid "
                "JSON — file is corrupted."
            ) from e

    def save(self, storage_state: dict[str, Any]) -> None:
        """Encrypt and persist the given Playwright storage_state dict.

        Writes to a temp file and renames over the target so a crash
        mid-write never leaves a half-written (and therefore corrupted, per
        `load()`'s empty/invalid-JSON checks) session file.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(storage_state).encode()
        encrypted = self._fernet.encrypt(payload)

        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_bytes(encrypted)
        os.replace(tmp_path, self._path)  # atomic on POSIX and Windows

    def clear(self) -> None:
        """Delete the stored session — used when a ban/invalidation is
        detected and the next attempt must go through a fresh login rather
        than retry with cookies that are now known-bad."""
        self._path.unlink(missing_ok=True)
