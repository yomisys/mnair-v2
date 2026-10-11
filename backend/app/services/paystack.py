"""
Thin Paystack client — the two calls MNAIR needs plus webhook signature
checking. Paystack is the default Nigerian gateway and one checkout page
covers card, bank transfer and USSD, which matters for learners without
cards.

Docs: https://paystack.com/docs/api/transaction/
"""

from __future__ import annotations
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    """Paystack unreachable, misconfigured, or refused the request."""


class PaystackClient:
    def __init__(self, settings: Settings, http: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self._http = http

    @property
    def enabled(self) -> bool:
        return self.settings.payments_configured

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.enabled:
            raise PaystackError("Paystack is not configured (PAYSTACK_SECRET_KEY unset)")
        url = f"{self.settings.PAYSTACK_BASE_URL.rstrip('/')}{path}"
        client = self._http or httpx.AsyncClient()
        try:
            response = await client.request(method, url, json=json, headers=self._headers(), timeout=20.0)
        except httpx.HTTPError as exc:
            logger.error("Paystack %s %s failed: %s", method, path, exc)
            raise PaystackError("Payment service unreachable") from exc
        finally:
            if self._http is None:
                await client.aclose()

        try:
            body = response.json()
        except ValueError as exc:
            raise PaystackError(f"Paystack returned non-JSON (HTTP {response.status_code})") from exc

        if response.status_code >= 400 or not body.get("status"):
            logger.error("Paystack %s %s refused: %s %s", method, path, response.status_code, body.get("message"))
            raise PaystackError(body.get("message") or f"Paystack error (HTTP {response.status_code})")
        return body.get("data") or {}

    async def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        reference: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start a checkout. Returns {authorization_url, access_code, reference}."""
        return await self._request("POST", "/transaction/initialize", {
            "email": email,
            "amount": amount_kobo,
            "currency": "NGN",
            "reference": reference,
            "callback_url": self.settings.payment_callback_url,
            "metadata": metadata or {},
        })

    async def verify(self, reference: str) -> Dict[str, Any]:
        """Authoritative transaction status (status, amount, currency, channel...)."""
        return await self._request("GET", f"/transaction/verify/{reference}")

    @staticmethod
    def signature_valid(secret: Optional[str], raw_body: bytes, signature: Optional[str]) -> bool:
        """Paystack signs the raw webhook body: HMAC-SHA512(secret) hex in
        the x-paystack-signature header."""
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)
