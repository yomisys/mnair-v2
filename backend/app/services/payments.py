"""
Payment flows on top of Paystack: start a checkout, then confirm it (from
the webhook or the payer's return to the callback page — whichever comes
first; confirmation is idempotent) and fulfil what was bought.
"""

from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.certificate import Certificate
from app.models.sponsor import (
    CertificateAccess,
    Organization,
    Payment,
    PaymentPurpose,
    PaymentStatus,
)
from app.models.user import User
from app.services.paystack import PaystackClient, PaystackError

logger = logging.getLogger(__name__)

# A pending checkout link is reused for this long so a learner tapping
# "Pay" twice doesn't create two transactions.
REUSE_PENDING_FOR = timedelta(hours=6)

_PREFIX = {
    PaymentPurpose.CERTIFICATE.value: "CRT",
    PaymentPurpose.SPONSOR_DEPOSIT.value: "DEP",
    PaymentPurpose.SPONSOR_BALANCE.value: "BAL",
    PaymentPurpose.SPONSOR_MANUAL.value: "MAN",
}


def new_reference(purpose: str) -> str:
    return f"MNAIR-{_PREFIX.get(purpose, 'PAY')}-{secrets.token_hex(8).upper()}"


def learner_email(settings: Settings, user: User) -> str:
    return f"learner-{user.id}@{settings.PAYSTACK_PLACEHOLDER_EMAIL_DOMAIN}"


def format_naira(kobo: int) -> str:
    naira = kobo / 100
    return f"₦{naira:,.0f}" if naira == int(naira) else f"₦{naira:,.2f}"


async def has_paid_for_certificate(db: AsyncSession, user_id: int) -> bool:
    return (await db.execute(
        select(Payment.id).where(
            Payment.user_id == user_id,
            Payment.purpose == PaymentPurpose.CERTIFICATE.value,
            Payment.status == PaymentStatus.SUCCESS.value,
        )
    )).first() is not None


async def _initialize(
    db: AsyncSession,
    client: PaystackClient,
    payment: Payment,
    metadata: Dict[str, Any],
) -> Payment:
    db.add(payment)
    await db.flush()
    try:
        data = await client.initialize(
            email=payment.email,
            amount_kobo=payment.amount_kobo,
            reference=payment.reference,
            metadata={"purpose": payment.purpose, **metadata},
        )
    except PaystackError:
        payment.status = PaymentStatus.FAILED.value
        payment.gateway_response = "initialize failed"
        await db.commit()
        raise
    payment.authorization_url = data.get("authorization_url")
    payment.access_code = data.get("access_code")
    await db.commit()
    await db.refresh(payment)
    return payment


async def start_certificate_payment(
    db: AsyncSession, settings: Settings, user: User, client: Optional[PaystackClient] = None
) -> Payment:
    """Checkout for a learner's own verified certificate. Reuses a recent
    pending link. Raises PaystackError when payments are unavailable."""
    client = client or PaystackClient(settings)
    if not client.enabled:
        raise PaystackError("Payments are not configured")

    recent = (await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.purpose == PaymentPurpose.CERTIFICATE.value,
            Payment.status == PaymentStatus.PENDING.value,
            Payment.authorization_url.is_not(None),
            Payment.amount_kobo == settings.CERTIFICATE_PRICE_KOBO,
            Payment.created_at >= datetime.utcnow() - REUSE_PENDING_FOR,
        ).order_by(Payment.created_at.desc())
    )).scalars().first()
    if recent:
        return recent

    payment = Payment(
        reference=new_reference(PaymentPurpose.CERTIFICATE.value),
        purpose=PaymentPurpose.CERTIFICATE.value,
        amount_kobo=settings.CERTIFICATE_PRICE_KOBO,
        user_id=user.id,
        email=learner_email(settings, user),
    )
    return await _initialize(db, client, payment, {"user_id": user.id})


async def start_sponsor_payment(
    db: AsyncSession,
    settings: Settings,
    org: Organization,
    purpose: str,
    amount_kobo: int,
    client: Optional[PaystackClient] = None,
) -> Payment:
    if purpose not in (PaymentPurpose.SPONSOR_DEPOSIT.value, PaymentPurpose.SPONSOR_BALANCE.value):
        raise ValueError("Unsupported sponsor payment purpose")
    if amount_kobo < 10_000:  # ₦100 floor — Paystack's practical minimum
        raise ValueError("Amount is too small to pay online")
    client = client or PaystackClient(settings)
    if not client.enabled:
        raise PaystackError("Payments are not configured")
    payment = Payment(
        reference=new_reference(purpose),
        purpose=purpose,
        amount_kobo=amount_kobo,
        organization_id=org.id,
        email=org.contact_email,
    )
    return await _initialize(db, client, payment, {"organization_id": org.id, "organization": org.name})


async def record_manual_payment(
    db: AsyncSession, org: Organization, amount_kobo: int, note: str, paid_at: Optional[datetime] = None
) -> Payment:
    """A bank transfer made outside Paystack, entered by an admin."""
    if amount_kobo <= 0:
        raise ValueError("Amount must be positive")
    payment = Payment(
        reference=new_reference(PaymentPurpose.SPONSOR_MANUAL.value),
        purpose=PaymentPurpose.SPONSOR_MANUAL.value,
        status=PaymentStatus.SUCCESS.value,
        amount_kobo=amount_kobo,
        organization_id=org.id,
        email=org.contact_email,
        channel="bank_transfer",
        note=note[:255],
        paid_at=paid_at or datetime.utcnow(),
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def _fulfil(db: AsyncSession, payment: Payment) -> None:
    """Deliver what was bought. Sponsor payments need nothing — the
    statement reads them directly."""
    if payment.purpose == PaymentPurpose.CERTIFICATE.value and payment.user_id:
        certificate = (await db.execute(
            select(Certificate).where(Certificate.user_id == payment.user_id)
        )).scalar_one_or_none()
        # No certificate yet is fine: the generator sees the paid row and
        # issues it as PAID.
        if certificate and certificate.access_type == CertificateAccess.PENDING_PAYMENT.value:
            certificate.access_type = CertificateAccess.PAID.value


def _parse_paid_at(value: Optional[str]) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.utcnow()


async def confirm_payment(
    db: AsyncSession,
    settings: Settings,
    reference: str,
    data: Optional[Dict[str, Any]] = None,
    client: Optional[PaystackClient] = None,
) -> Optional[Payment]:
    """Apply a transaction's outcome. `data` is the webhook's (already
    signature-checked) payload; without it, ask Paystack. Returns None for a
    reference we never issued. Safe to call any number of times."""
    payment = (await db.execute(
        select(Payment).where(Payment.reference == reference).with_for_update()
    )).scalar_one_or_none()
    if not payment:
        return None
    if payment.status == PaymentStatus.SUCCESS.value:
        return payment

    if data is None:
        data = await (client or PaystackClient(settings)).verify(reference)

    gateway_status = (data.get("status") or "").lower()
    payment.gateway_response = (data.get("gateway_response") or "")[:255] or None
    payment.channel = data.get("channel") or payment.channel

    if gateway_status == "success":
        amount = int(data.get("amount") or 0)
        currency = (data.get("currency") or "NGN").upper()
        if amount != payment.amount_kobo or currency != payment.currency:
            # Never fulfil a tampered or partial amount. Leave it pending
            # for a human to look at.
            logger.error(
                "Payment %s amount mismatch: expected %s %s, got %s %s",
                reference, payment.amount_kobo, payment.currency, amount, currency,
            )
            payment.note = f"amount mismatch: got {amount} {currency}"
            await db.commit()
            return payment
        payment.status = PaymentStatus.SUCCESS.value
        payment.paid_at = _parse_paid_at(data.get("paid_at") or data.get("paidAt"))
        await _fulfil(db, payment)
    elif gateway_status in ("failed", "reversed"):
        payment.status = PaymentStatus.FAILED.value
    elif gateway_status == "abandoned":
        payment.status = PaymentStatus.ABANDONED.value

    await db.commit()
    await db.refresh(payment)
    return payment
