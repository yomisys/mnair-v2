"""
Payments: learner certificate checkout, the Paystack webhook, and the
status check the /payment/callback page calls when the payer comes back.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.rate_limit import PUBLIC_RATE_LIMIT, WEBHOOK_RATE_LIMIT, STRICT_RATE_LIMIT, limiter
from app.models.certificate import Certificate
from app.models.user import User, UserRole
from app.schemas.sponsor import CheckoutOut, PaymentStatusOut
from app.services.payments import confirm_payment, start_certificate_payment
from app.services.paystack import PaystackClient, PaystackError
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])

WEBHOOK_PATH = "/api/v1/payments/paystack/webhook"


@router.post("/certificate", response_model=CheckoutOut)
@limiter.limit(STRICT_RATE_LIMIT)
async def certificate_checkout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Start (or resume) checkout for the learner's verified certificate."""
    if user.role != UserRole.LEARNER:
        raise HTTPException(status_code=403, detail="Learner account required")
    if not settings.CERTIFICATE_PAYWALL_ENABLED:
        raise HTTPException(status_code=409, detail="Certificates are free right now — no payment needed")
    if user.sponsor_code_id:
        raise HTTPException(status_code=409, detail="Your certificate is paid for by your sponsor")
    if (user.completed_days or 0) < 7:
        raise HTTPException(status_code=409, detail="Finish all 7 days first")
    cert = (await db.execute(select(Certificate).where(Certificate.user_id == user.id))).scalar_one_or_none()
    if cert and cert.is_verified:
        raise HTTPException(status_code=409, detail="Your certificate is already unlocked")

    try:
        payment = await start_certificate_payment(db, settings, user)
    except PaystackError:
        raise HTTPException(status_code=503, detail="Payments are unavailable right now. Please try again later.")
    return CheckoutOut(
        reference=payment.reference,
        authorization_url=payment.authorization_url,
        amount_kobo=payment.amount_kobo,
        purpose=payment.purpose,
    )


@router.get("/verify/{reference}", response_model=PaymentStatusOut)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def verify_payment(
    request: Request,
    reference: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Called by the callback page. Re-checks with Paystack, so it works
    even if the webhook hasn't arrived (or never does). Returns only the
    status — no payer details."""
    if len(reference) > 100:
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        payment = await confirm_payment(db, settings, reference)
    except PaystackError:
        raise HTTPException(status_code=503, detail="Couldn't reach the payment service. Refresh in a minute.")
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentStatusOut(
        reference=payment.reference,
        status=payment.status,
        purpose=payment.purpose,
        amount_kobo=payment.amount_kobo,
    )


@router.post("/paystack/webhook")
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Paystack event receiver. Signature-checked against the raw body;
    only charge.success changes anything. Always 200 for a valid signature
    so Paystack stops retrying events we deliberately ignore."""
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not PaystackClient.signature_valid(settings.PAYSTACK_SECRET_KEY, raw, signature):
        logger.warning("Paystack webhook with bad signature rejected")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if event.get("event") == "charge.success":
        data = event.get("data") or {}
        reference = data.get("reference")
        if reference:
            payment = await confirm_payment(db, settings, reference, data=data)
            if payment is None:
                logger.warning("Paystack webhook for unknown reference %s", reference)
    return {"status": "ok"}
