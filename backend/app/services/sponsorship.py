"""
Sponsorship rules: redeeming a code, billing a certificate to a sponsor,
and the numbers a sponsor sees (dashboard + statement).

Every money figure is kobo. Billing is derived from SponsorCharge and
Payment rows at read time (see app.models.sponsor for why).
"""

from __future__ import annotations
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.sponsor import (
    CertificateAccess,
    Organization,
    Payment,
    PaymentPurpose,
    PaymentStatus,
    SponsorCharge,
    SponsorCode,
)
from app.models.user import User

CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,39}$")

SPONSOR_PAYMENT_PURPOSES = (
    PaymentPurpose.SPONSOR_DEPOSIT.value,
    PaymentPurpose.SPONSOR_BALANCE.value,
    PaymentPurpose.SPONSOR_MANUAL.value,
)


class SponsorCodeError(Exception):
    """Raised with a learner-facing message when a code can't be applied."""


@dataclass
class RedeemResult:
    organization: Organization
    code: SponsorCode
    already_applied: bool = False


def normalize_code(raw: str) -> str:
    return re.sub(r"[\s_]+", "", (raw or "")).upper()


def generate_code(prefix: str) -> str:
    """PREFIX-XXXX from an org name, e.g. 'Grace Chapel' -> GRACECHAP-7K2Q."""
    base = re.sub(r"[^A-Z0-9]", "", prefix.upper())[:10] or "MNAIR"
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I — read aloud from a pulpit
    return f"{base}-{''.join(secrets.choice(alphabet) for _ in range(4))}"


async def _enrolled_count_for_org(db: AsyncSession, org_id: int) -> int:
    return (await db.execute(
        select(func.count(User.id))
        .join(SponsorCode, User.sponsor_code_id == SponsorCode.id)
        .where(SponsorCode.organization_id == org_id)
    )).scalar_one()


async def _enrolled_count_for_code(db: AsyncSession, code_id: int) -> int:
    return (await db.execute(
        select(func.count(User.id)).where(User.sponsor_code_id == code_id)
    )).scalar_one()


async def get_sponsor_for_user(db: AsyncSession, user: User) -> Optional[Organization]:
    if not user.sponsor_code_id:
        return None
    return (await db.execute(
        select(Organization)
        .join(SponsorCode, SponsorCode.organization_id == Organization.id)
        .where(SponsorCode.id == user.sponsor_code_id)
    )).scalar_one_or_none()


async def check_code(db: AsyncSession, raw_code: str, lock: bool = False):
    """Validate a code is usable right now. Returns (code, organization) or
    raises SponsorCodeError with a learner-facing message. With lock=True
    the sponsor row is locked (FOR UPDATE on PostgreSQL, no-op on SQLite)
    so two learners can't both take the last place."""
    code_str = normalize_code(raw_code)
    if not CODE_PATTERN.match(code_str):
        raise SponsorCodeError("That doesn't look like a sponsor code. Check it and try again.")

    code = (await db.execute(select(SponsorCode).where(SponsorCode.code == code_str))).scalar_one_or_none()
    if not code:
        raise SponsorCodeError("We couldn't find that sponsor code. Check it and try again.")

    org_q = select(Organization).where(Organization.id == code.organization_id)
    if lock:
        org_q = org_q.with_for_update()
    org = (await db.execute(org_q)).scalar_one()

    if not code.is_active or not org.is_active:
        raise SponsorCodeError("This sponsor code is no longer active.")
    if code.expires_at and code.expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise SponsorCodeError("This sponsor code has expired.")
    if code.max_enrolments is not None and await _enrolled_count_for_code(db, code.id) >= code.max_enrolments:
        raise SponsorCodeError("This sponsor code has reached its limit.")
    if org.learner_cap is not None and await _enrolled_count_for_org(db, org.id) >= org.learner_cap:
        raise SponsorCodeError("This sponsor's places are all taken.")
    return code, org


async def redeem_code(db: AsyncSession, user: User, raw_code: str) -> RedeemResult:
    """Attach a learner to a sponsor. Commits on success.

    A learner belongs to one sponsor for good (no shopping around once
    billing has started). A learner who already holds a verified
    certificate can't be billed to a sponsor after the fact; one whose
    certificate is waiting for payment is converted to sponsored here.
    """
    if user.sponsor_code_id:
        current = await get_sponsor_for_user(db, user)
        code_str = normalize_code(raw_code)
        same = current and (await db.execute(
            select(SponsorCode).where(SponsorCode.code == code_str, SponsorCode.organization_id == current.id)
        )).scalar_one_or_none()
        if same:
            return RedeemResult(organization=current, code=same, already_applied=True)
        raise SponsorCodeError("Your account is already linked to a sponsor.")

    code, org = await check_code(db, raw_code, lock=True)

    certificate = (await db.execute(
        select(Certificate).where(Certificate.user_id == user.id)
    )).scalar_one_or_none()
    if certificate and certificate.access_type != CertificateAccess.PENDING_PAYMENT.value:
        raise SponsorCodeError("You already have your certificate, so a sponsor code can't be added now.")

    user.sponsor_code_id = code.id
    user.sponsored_at = datetime.utcnow()
    if certificate:
        await bill_certificate(db, user, certificate, org=org, code_id=code.id)
    await db.commit()
    return RedeemResult(organization=org, code=code)


async def bill_certificate(
    db: AsyncSession,
    user: User,
    certificate: Certificate,
    org: Optional[Organization] = None,
    code_id: Optional[int] = None,
) -> Optional[Organization]:
    """Mark a certificate sponsored and write its charge (idempotent on the
    certificate code). Caller commits. Returns the sponsor, or None when the
    learner has no sponsor."""
    org = org or await get_sponsor_for_user(db, user)
    if not org:
        return None

    certificate.access_type = CertificateAccess.SPONSORED.value
    certificate.organization_id = org.id
    certificate.sponsor_name = org.name

    exists = (await db.execute(
        select(SponsorCharge.id).where(SponsorCharge.certificate_code == certificate.certificate_id)
    )).first()
    if not exists:
        db.add(SponsorCharge(
            organization_id=org.id,
            sponsor_code_id=code_id or user.sponsor_code_id,
            user_id=user.id,
            certificate_code=certificate.certificate_id,
            amount_kobo=org.price_per_certificate_kobo,
        ))
    return org


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

async def _sum_charges(db: AsyncSession, org_id: int, before: Optional[datetime] = None, since: Optional[datetime] = None):
    q = select(func.count(SponsorCharge.id), func.coalesce(func.sum(SponsorCharge.amount_kobo), 0)).where(
        SponsorCharge.organization_id == org_id
    )
    if before:
        q = q.where(SponsorCharge.created_at < before)
    if since:
        q = q.where(SponsorCharge.created_at >= since)
    count, total = (await db.execute(q)).one()
    return int(count), int(total)


async def _sum_payments(db: AsyncSession, org_id: int, before: Optional[datetime] = None, since: Optional[datetime] = None) -> int:
    q = select(func.coalesce(func.sum(Payment.amount_kobo), 0)).where(
        Payment.organization_id == org_id,
        Payment.status == PaymentStatus.SUCCESS.value,
        Payment.purpose.in_(SPONSOR_PAYMENT_PURPOSES),
    )
    paid_at = func.coalesce(Payment.paid_at, Payment.created_at)
    if before:
        q = q.where(paid_at < before)
    if since:
        q = q.where(paid_at >= since)
    return int((await db.execute(q)).scalar_one())


async def account_summary(db: AsyncSession, org: Organization) -> Dict[str, int]:
    certificates, charged = await _sum_charges(db, org.id)
    paid = await _sum_payments(db, org.id)
    deposit_paid = int((await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kobo), 0)).where(
            Payment.organization_id == org.id,
            Payment.status == PaymentStatus.SUCCESS.value,
            Payment.purpose == PaymentPurpose.SPONSOR_DEPOSIT.value,
        )
    )).scalar_one())
    return {
        "certificates_billed": certificates,
        "charged_kobo": charged,
        "paid_kobo": paid,
        "deposit_paid_kobo": deposit_paid,
        "deposit_outstanding_kobo": max(0, org.deposit_kobo - deposit_paid),
        "credit_remaining_kobo": max(0, paid - charged),
        "amount_due_kobo": max(0, charged - paid),
    }


def _month_bounds(year: int, month: int):
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), (month % 12) + 1, 1)
    return start, end


async def monthly_statement(db: AsyncSession, org: Organization, year: int, month: int) -> Dict[str, Any]:
    """Opening balance, certificates and payments in the month, closing
    balance. Balance > 0 = owed by the sponsor; < 0 = credit (deposit left)."""
    start, end = _month_bounds(year, month)
    _, charged_before = await _sum_charges(db, org.id, before=start)
    paid_before = await _sum_payments(db, org.id, before=start)
    count, charged = await _sum_charges(db, org.id, since=start, before=end)
    paid = await _sum_payments(db, org.id, since=start, before=end)

    lines = (await db.execute(
        select(SponsorCharge.certificate_code, SponsorCharge.amount_kobo, SponsorCharge.created_at)
        .where(
            SponsorCharge.organization_id == org.id,
            SponsorCharge.created_at >= start,
            SponsorCharge.created_at < end,
        )
        .order_by(SponsorCharge.created_at)
    )).all()
    payments = (await db.execute(
        select(Payment).where(
            Payment.organization_id == org.id,
            Payment.status == PaymentStatus.SUCCESS.value,
            Payment.purpose.in_(SPONSOR_PAYMENT_PURPOSES),
            func.coalesce(Payment.paid_at, Payment.created_at) >= start,
            func.coalesce(Payment.paid_at, Payment.created_at) < end,
        ).order_by(Payment.paid_at)
    )).scalars().all()

    opening = charged_before - paid_before
    closing = opening + charged - paid
    return {
        "organization": org.name,
        "period": f"{year:04d}-{month:02d}",
        "price_per_certificate_kobo": org.price_per_certificate_kobo,
        "opening_balance_kobo": opening,
        "certificates_issued": count,
        "charges_kobo": charged,
        "payments_kobo": paid,
        "closing_balance_kobo": closing,
        "amount_due_kobo": max(0, closing),
        "charges": [
            {"certificate_id": c, "amount_kobo": a, "issued_at": t.isoformat()} for c, a, t in lines
        ],
        "payments": [
            {
                "reference": p.reference,
                "purpose": p.purpose,
                "amount_kobo": p.amount_kobo,
                "channel": p.channel,
                "paid_at": (p.paid_at or p.created_at).isoformat(),
            }
            for p in payments
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _learners_query(org_id: int):
    return (
        select(User, Certificate.certificate_id, Certificate.access_type)
        .join(SponsorCode, User.sponsor_code_id == SponsorCode.id)
        .outerjoin(Certificate, Certificate.user_id == User.id)
        .where(SponsorCode.organization_id == org_id)
    )


async def dashboard(db: AsyncSession, org: Organization) -> Dict[str, Any]:
    """Aggregate progress for a sponsor. No phone numbers, by design (NDPA
    data minimisation — the sponsor is paying for outcomes, not contacts)."""
    week_ago = datetime.utcnow() - timedelta(days=7)
    in_org = and_(User.sponsor_code_id == SponsorCode.id, SponsorCode.organization_id == org.id)

    enrolled = await _enrolled_count_for_org(db, org.id)
    active = (await db.execute(
        select(func.count(User.id)).select_from(User).join(SponsorCode, in_org)
        .where(User.last_active_at >= week_ago)
    )).scalar_one()
    by_day = dict((await db.execute(
        select(User.completed_days, func.count(User.id)).select_from(User).join(SponsorCode, in_org)
        .group_by(User.completed_days)
    )).all())
    by_language = (await db.execute(
        select(User.language, func.count(User.id)).select_from(User).join(SponsorCode, in_org)
        .group_by(User.language)
    )).all()
    by_code = (await db.execute(
        select(SponsorCode.code, SponsorCode.label, SponsorCode.max_enrolments, SponsorCode.is_active, func.count(User.id))
        .outerjoin(User, User.sponsor_code_id == SponsorCode.id)
        .where(SponsorCode.organization_id == org.id)
        .group_by(SponsorCode.id)
        .order_by(SponsorCode.created_at)
    )).all()
    avg_score = (await db.execute(
        select(func.avg(Certificate.average_quiz_score)).where(
            Certificate.organization_id == org.id
        )
    )).scalar_one()

    account = await account_summary(db, org)
    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "package": org.package,
            "price_per_certificate_kobo": org.price_per_certificate_kobo,
            "deposit_kobo": org.deposit_kobo,
            "learner_cap": org.learner_cap,
            "has_logo": bool(org.logo_object),
        },
        "learners": {
            "enrolled": enrolled,
            "active_last_7_days": active,
            "certified": account["certificates_billed"],
            "completion_rate": round(100 * account["certificates_billed"] / enrolled, 1) if enrolled else 0.0,
            "average_quiz_score": round(float(avg_score), 1) if avg_score is not None else None,
            "days_completed": {str(d): int(by_day.get(d, 0)) for d in range(0, 8)},
            "by_language": {
                (lang.value if hasattr(lang, "value") else str(lang)): n for lang, n in by_language
            },
        },
        "codes": [
            {"code": c, "label": l, "max_enrolments": m, "is_active": a, "enrolled": n}
            for c, l, m, a, n in by_code
        ],
        "account": account,
    }


async def learner_list(
    db: AsyncSession, org: Organization, offset: int = 0, limit: int = 50, admin_view: bool = False
) -> Dict[str, Any]:
    """admin_view adds the learner id and any certificate (not only the
    sponsored one) so the admin can open the learner record. The sponsor's
    own view never carries ids or contacts."""
    total = await _enrolled_count_for_org(db, org.id)
    rows = (await db.execute(
        _learners_query(org.id).order_by(User.sponsored_at.desc(), User.id.desc()).offset(offset).limit(limit)
    )).all()
    items = []
    for u, cert_id, access in rows:
        item = {
            "name": u.name if u.name_confirmed else "Learner (name not set yet)",
            "language": u.language.value if hasattr(u.language, "value") else str(u.language),
            "current_day": u.current_day,
            "completed_days": u.completed_days or 0,
            "certified": bool(cert_id) and access == CertificateAccess.SPONSORED.value,
            "certificate_id": cert_id if access == CertificateAccess.SPONSORED.value else None,
            "joined_at": u.sponsored_at.isoformat() if u.sponsored_at else None,
            "last_active_at": u.last_active_at.isoformat() if u.last_active_at else None,
        }
        if admin_view:
            item.update({
                "user_id": u.id,
                "is_active": u.is_active,
                "any_certificate_id": cert_id,
                "certificate_access": access,
            })
        items.append(item)
    return {"total": total, "items": items}


async def organization_list(db: AsyncSession) -> List[Dict[str, Any]]:
    orgs = (await db.execute(select(Organization).order_by(Organization.created_at.desc()))).scalars().all()
    out = []
    for org in orgs:
        account = await account_summary(db, org)
        out.append({
            "id": org.id,
            "name": org.name,
            "package": org.package,
            "is_active": org.is_active,
            "price_per_certificate_kobo": org.price_per_certificate_kobo,
            "deposit_kobo": org.deposit_kobo,
            "learner_cap": org.learner_cap,
            "enrolled": await _enrolled_count_for_org(db, org.id),
            "contact_email": org.contact_email,
            "portal_email": org.portal_email,
            **account,
        })
    return out
