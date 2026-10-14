"""
Admin back office: platform overview (learners + money), learner
management, certificates (download / share link), the payments ledger and
the audit log. Sponsor management lives in app.routers.sponsors.

Every change made here writes an AdminAuditLog row in the same commit.
"""

from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models.audit import AdminAuditLog
from app.models.certificate import Certificate
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt
from app.models.sponsor import (
    Organization,
    Payment,
    PaymentPurpose,
    PaymentStatus,
    SponsorCharge,
    SponsorCode,
)
from app.models.user import Language, User, UserRole
from app.schemas.admin import CertificateLinkRequest, LearnerUpdate, VoidPaymentRequest
from app.services import audit, certificate_files
from app.services.sponsorship import SPONSOR_PAYMENT_PURPOSES
from app.utils.auth import get_current_admin_user, get_password_hash

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


def _enum(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if v else None


def _month_key(d: datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _last_months(n: int) -> List[str]:
    now = datetime.utcnow()
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------

@router.get("/overview")
async def overview(_: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    """Headline numbers for the dashboard: learners and money, in one call."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    learner = User.role == UserRole.LEARNER

    async def count(*where) -> int:
        return int((await db.execute(select(func.count(User.id)).where(learner, *where))).scalar_one())

    learners = {
        "total": await count(),
        "active_last_7_days": await count(User.last_active_at >= week_ago),
        "new_last_7_days": await count(User.created_at >= week_ago),
        "inactive_accounts": await count(User.is_active.is_(False)),
        "sponsored": await count(User.sponsor_code_id.is_not(None)),
        "completed_course": await count(User.completed_days >= 7),
        "certificates_issued": int((await db.execute(select(func.count(Certificate.id)))).scalar_one()),
    }

    # Per-sponsor charged/paid so "outstanding" never nets one sponsor's credit
    # against another's debt
    charged_by_org = dict((await db.execute(
        select(SponsorCharge.organization_id, func.sum(SponsorCharge.amount_kobo)).group_by(SponsorCharge.organization_id)
    )).all())
    paid_by_org = dict((await db.execute(
        select(Payment.organization_id, func.sum(Payment.amount_kobo))
        .where(Payment.status == PaymentStatus.SUCCESS.value, Payment.purpose.in_(SPONSOR_PAYMENT_PURPOSES))
        .group_by(Payment.organization_id)
    )).all())
    deposit_paid_by_org = dict((await db.execute(
        select(Payment.organization_id, func.sum(Payment.amount_kobo))
        .where(Payment.status == PaymentStatus.SUCCESS.value, Payment.purpose == PaymentPurpose.SPONSOR_DEPOSIT.value)
        .group_by(Payment.organization_id)
    )).all())
    orgs = (await db.execute(select(Organization.id, Organization.deposit_kobo, Organization.is_active))).all()

    outstanding = sum(max(0, int(charged_by_org.get(o.id) or 0) - int(paid_by_org.get(o.id) or 0)) for o in orgs)
    credit = sum(max(0, int(paid_by_org.get(o.id) or 0) - int(charged_by_org.get(o.id) or 0)) for o in orgs)
    deposits_outstanding = sum(
        max(0, (o.deposit_kobo or 0) - int(deposit_paid_by_org.get(o.id) or 0)) for o in orgs if o.is_active
    )
    sponsors_owing = sum(
        1 for o in orgs if int(charged_by_org.get(o.id) or 0) > int(paid_by_org.get(o.id) or 0)
    )

    success = Payment.status == PaymentStatus.SUCCESS.value
    sponsor_collected = int((await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kobo), 0)).where(success, Payment.purpose.in_(SPONSOR_PAYMENT_PURPOSES))
    )).scalar_one())
    learner_collected = int((await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kobo), 0)).where(success, Payment.purpose == PaymentPurpose.CERTIFICATE.value)
    )).scalar_one())
    collected_30d = int((await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kobo), 0)).where(
            success, func.coalesce(Payment.paid_at, Payment.created_at) >= month_ago
        )
    )).scalar_one())
    pending_payments = int((await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING.value)
    )).scalar_one())

    # Six-month trend, bucketed in Python so it reads the same on SQLite and PostgreSQL
    months = _last_months(6)
    since = datetime.strptime(months[0] + "-01", "%Y-%m-%d")
    trend: Dict[str, Dict[str, int]] = {m: {"charged_kobo": 0, "collected_kobo": 0, "certificates": 0} for m in months}
    for created_at, amount in (await db.execute(
        select(SponsorCharge.created_at, SponsorCharge.amount_kobo).where(SponsorCharge.created_at >= since)
    )).all():
        key = _month_key(created_at)
        if key in trend:
            trend[key]["charged_kobo"] += amount
    for when, amount in (await db.execute(
        select(func.coalesce(Payment.paid_at, Payment.created_at), Payment.amount_kobo)
        .where(success, func.coalesce(Payment.paid_at, Payment.created_at) >= since)
    )).all():
        key = _month_key(when)
        if key in trend:
            trend[key]["collected_kobo"] += amount
    for (issued_at,) in (await db.execute(select(Certificate.issued_at).where(Certificate.issued_at >= since))).all():
        key = _month_key(issued_at)
        if key in trend:
            trend[key]["certificates"] += 1

    return {
        "learners": learners,
        "sponsors": {
            "total": len(orgs),
            "active": sum(1 for o in orgs if o.is_active),
            "owing": sponsors_owing,
        },
        "revenue": {
            "charged_kobo": sum(int(v or 0) for v in charged_by_org.values()),
            "sponsor_collected_kobo": sponsor_collected,
            "learner_certificate_collected_kobo": learner_collected,
            "total_collected_kobo": sponsor_collected + learner_collected,
            "outstanding_kobo": outstanding,
            "sponsor_credit_kobo": credit,
            "deposits_outstanding_kobo": deposits_outstanding,
            "collected_last_30_days_kobo": collected_30d,
            "pending_payments": pending_payments,
        },
        "trend": [{"month": m, **trend[m]} for m in months],
    }


# ---------------------------------------------------------------------------
# learners
# ---------------------------------------------------------------------------

def _latest_cert(column):
    """Correlated subquery: a column of the learner's most recent certificate."""
    return (
        select(column)
        .where(Certificate.user_id == User.id)
        .order_by(Certificate.issued_at.desc())
        .limit(1)
        .correlate(User)
        .scalar_subquery()
    )


def _phone_variants(q: str) -> List[str]:
    digits = "".join(ch for ch in q if ch.isdigit())
    out = [q]
    if digits.startswith("0") and len(digits) > 1:
        out.append("+234" + digits[1:])
    elif digits.startswith("234"):
        out.append("+" + digits)
    return out


@router.get("/learners")
async def list_learners(
    q: Optional[str] = Query(None, max_length=100, description="Name, phone or email"),
    status: Optional[str] = Query(None, pattern="^(active|inactive)$"),
    role: Optional[UserRole] = None,
    language: Optional[Language] = None,
    channel: Optional[str] = Query(None, max_length=20),
    sponsor_id: Optional[int] = None,
    certified: Optional[bool] = None,
    sort: str = Query("newest", pattern="^(newest|oldest|last_active|progress|name)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=200),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-side paged, so the list stays fast at 100k learners."""
    cert_id = _latest_cert(Certificate.certificate_id).label("certificate_id")
    cert_access = _latest_cert(Certificate.access_type).label("certificate_access")

    filters = []
    if q:
        q = q.strip()
        like = [User.phone_number.ilike(f"%{v}%") for v in _phone_variants(q)]
        filters.append(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"), *like))
    if status:
        filters.append(User.is_active.is_(status == "active"))
    if role:
        filters.append(User.role == role)
    if language:
        filters.append(User.language == language)
    if channel:
        filters.append(User.preferred_channel == channel)
    if sponsor_id is not None:
        filters.append(SponsorCode.organization_id == sponsor_id)
    if certified is not None:
        has_cert = select(Certificate.id).where(Certificate.user_id == User.id).correlate(User).exists()
        filters.append(has_cert if certified else ~has_cert)

    base = (
        select(User.id)
        .outerjoin(SponsorCode, User.sponsor_code_id == SponsorCode.id)
        .where(*filters)
    )
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())

    order = {
        "newest": [User.created_at.desc(), User.id.desc()],
        "oldest": [User.created_at.asc(), User.id.asc()],
        "last_active": [User.last_active_at.desc().nulls_last(), User.id.desc()],
        "progress": [User.completed_days.desc(), User.current_day.desc(), User.id.desc()],
        "name": [User.name.asc(), User.id.asc()],
    }[sort]
    rows = (await db.execute(
        select(User, Organization.id, Organization.name, SponsorCode.code, cert_id, cert_access)
        .outerjoin(SponsorCode, User.sponsor_code_id == SponsorCode.id)
        .outerjoin(Organization, SponsorCode.organization_id == Organization.id)
        .where(*filters)
        .order_by(*order)
        .offset(offset)
        .limit(limit)
    )).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "name_confirmed": u.name_confirmed,
                "phone_number": u.phone_number,
                "email": u.email,
                "role": _enum(u.role),
                "language": _enum(u.language),
                "current_day": u.current_day,
                "completed_days": u.completed_days or 0,
                "is_active": u.is_active,
                "preferred_channel": u.preferred_channel,
                "sponsor": {"id": oid, "name": oname, "code": code} if oid else None,
                "certificate_id": cid,
                "certificate_access": access,
                "created_at": _iso(u.created_at),
                "last_active_at": _iso(u.last_active_at),
            }
            for u, oid, oname, code, cid, access in rows
        ],
    }


async def _get_user(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Learner not found")
    return user


def _cert_out(c: Certificate) -> Dict[str, Any]:
    return {
        "certificate_id": c.certificate_id,
        "learner_name": c.learner_name,
        "language": c.language,
        "access_type": c.access_type,
        "is_verified": c.is_verified,
        "sponsor_name": c.sponsor_name,
        "organization_id": c.organization_id,
        "average_quiz_score": c.average_quiz_score,
        "days_to_complete": c.days_to_complete,
        "issued_at": _iso(c.issued_at),
    }


def _payment_out(p: Payment, org_name: Optional[str] = None, user_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "reference": p.reference,
        "purpose": p.purpose,
        "status": p.status,
        "amount_kobo": p.amount_kobo,
        "organization_id": p.organization_id,
        "organization_name": org_name,
        "user_id": p.user_id,
        "user_name": user_name,
        "email": p.email,
        "channel": p.channel,
        "note": p.note,
        "gateway_response": p.gateway_response,
        "paid_at": _iso(p.paid_at),
        "created_at": _iso(p.created_at),
    }


@router.get("/learners/{user_id}")
async def learner_detail(user_id: int, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    user = await _get_user(db, user_id)

    sponsor = None
    if user.sponsor_code_id:
        row = (await db.execute(
            select(SponsorCode, Organization)
            .join(Organization, Organization.id == SponsorCode.organization_id)
            .where(SponsorCode.id == user.sponsor_code_id)
        )).first()
        if row:
            code, org = row
            sponsor = {"id": org.id, "name": org.name, "code": code.code, "sponsored_at": _iso(user.sponsored_at)}

    certificates = (await db.execute(
        select(Certificate).where(Certificate.user_id == user.id).order_by(Certificate.issued_at.desc())
    )).scalars().all()

    lessons_completed = int((await db.execute(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user.id, LessonProgress.completed_at.is_not(None)
        )
    )).scalar_one())
    quiz = (await db.execute(
        select(
            func.count(QuizAttempt.id),
            func.coalesce(func.sum(QuizAttempt.correct_count), 0),
            func.coalesce(func.sum(QuizAttempt.questions_count), 0),
        ).where(QuizAttempt.user_id == user.id)
    )).one()
    quiz_attempts, quiz_correct, quiz_questions = int(quiz[0] or 0), int(quiz[1] or 0), int(quiz[2] or 0)

    payments = (await db.execute(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
    )).scalars().all()
    history = (await db.execute(
        select(AdminAuditLog)
        .where(AdminAuditLog.target_type == "learner", AdminAuditLog.target_id == str(user.id))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(20)
    )).scalars().all()

    return {
        "id": user.id,
        "name": user.name,
        "name_confirmed": user.name_confirmed,
        "phone_number": user.phone_number,
        "email": user.email,
        "role": _enum(user.role),
        "language": _enum(user.language),
        "is_active": user.is_active,
        "current_day": user.current_day,
        "completed_days": user.completed_days or 0,
        "preferred_channel": user.preferred_channel,
        "has_pin": bool(user.learner_pin_hash),
        "has_password": bool(user.hashed_password),
        "telegram_linked": bool(user.telegram_chat_id),
        "network_operator": user.network_operator,
        "consent_given": user.consent_given,
        "consent_date": _iso(user.consent_date),
        "created_at": _iso(user.created_at),
        "last_active_at": _iso(user.last_active_at),
        "sponsor": sponsor,
        "progress": {
            "lessons_completed": lessons_completed,
            "quiz_attempts": quiz_attempts,
            "quiz_correct": quiz_correct,
            "quiz_questions": quiz_questions,
            "quiz_accuracy": round(100 * quiz_correct / quiz_questions, 1) if quiz_questions else None,
        },
        "certificates": [_cert_out(c) for c in certificates],
        "payments": [_payment_out(p) for p in payments],
        "history": [_audit_out(a) for a in history],
    }


async def _active_admins(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    )).scalar_one())


@router.patch("/learners/{user_id}")
async def update_learner(
    user_id: int,
    body: LearnerUpdate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if not data and not password:
        raise HTTPException(status_code=422, detail="Nothing to change")

    removing_admin = user.role == UserRole.ADMIN and (
        data.get("is_active") is False or (data.get("role") not in (None, UserRole.ADMIN))
    )
    if removing_admin:
        if user.id == admin.id:
            raise HTTPException(status_code=409, detail="You can't deactivate or demote your own account")
        if await _active_admins(db) <= 1:
            raise HTTPException(status_code=409, detail="At least one active admin must remain")

    new_phone = data.get("phone_number")
    if new_phone and new_phone != user.phone_number:
        if user.phone_number.startswith(("tg:", "kc:")):
            raise HTTPException(
                status_code=409,
                detail="This learner signs in through Telegram/KingsChat, which identifies them by chat, not phone",
            )
        taken = (await db.execute(
            select(User.id).where(User.phone_number == new_phone, User.id != user.id)
        )).first()
        if taken:
            raise HTTPException(status_code=409, detail=f"{new_phone} already belongs to another account (#{taken[0]})")

    if "email" in data:
        data["email"] = (data["email"] or "").strip().lower() or None
        if data["email"] and (await db.execute(
            select(User.id).where(User.email == data["email"], User.id != user.id)
        )).first():
            raise HTTPException(status_code=409, detail="That email already belongs to another account")

    becomes_admin = data.get("role") == UserRole.ADMIN and user.role != UserRole.ADMIN
    if becomes_admin and not (password or user.hashed_password):
        raise HTTPException(status_code=422, detail="Set a password (10+ characters) so the new admin can sign in")

    changes: Dict[str, Any] = {}
    for key, value in data.items():
        old = getattr(user, key)
        if _enum(old) != _enum(value):
            changes[key] = {"from": _enum(old), "to": _enum(value)}
            setattr(user, key, value)
    if "name" in changes:
        user.name_confirmed = True
    if password:
        user.hashed_password = get_password_hash(password)
        changes["password"] = "(changed)"
    if not changes:
        return {"id": user.id, "updated": []}

    audit.record(
        db, admin, "learner.update",
        f"Updated {user.name} ({user.phone_number}): {', '.join(sorted(changes))}",
        target_type="learner", target_id=user.id, details=changes, request=request,
    )
    await db.commit()
    return {"id": user.id, "updated": sorted(changes)}


@router.post("/learners/{user_id}/reset-pin")
async def reset_learner_pin(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Clears the web PIN. The learner's next sign-in at /learn sets a new one
    (the same path learners who pre-date PINs take)."""
    user = await _get_user(db, user_id)
    if user.role != UserRole.LEARNER:
        raise HTTPException(status_code=409, detail="Only learner accounts have a PIN")
    user.learner_pin_hash = None
    audit.record(
        db, admin, "learner.reset_pin", f"Reset web PIN for {user.name} ({user.phone_number})",
        target_type="learner", target_id=user.id, request=request,
    )
    await db.commit()
    return {"id": user.id, "has_pin": False}


@router.post("/learners/{user_id}/remove-sponsor")
async def remove_learner_sponsor(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Detach a learner from a sponsor code (e.g. enrolled with the wrong
    code). A certificate already billed stays billed."""
    user = await _get_user(db, user_id)
    if not user.sponsor_code_id:
        raise HTTPException(status_code=409, detail="This learner isn't sponsored")
    code = (await db.execute(select(SponsorCode).where(SponsorCode.id == user.sponsor_code_id))).scalar_one_or_none()
    user.sponsor_code_id = None
    user.sponsored_at = None
    audit.record(
        db, admin, "learner.remove_sponsor",
        f"Removed {user.name} from sponsor code {code.code if code else '?'}",
        target_type="learner", target_id=user.id,
        details={"code": code.code if code else None, "organization_id": code.organization_id if code else None},
        request=request,
    )
    await db.commit()
    return {"id": user.id, "sponsor": None}


# ---------------------------------------------------------------------------
# certificates
# ---------------------------------------------------------------------------

@router.get("/certificates")
async def list_certificates(
    q: Optional[str] = Query(None, max_length=100, description="Certificate ID or learner name"),
    access_type: Optional[str] = Query(None, max_length=20),
    sponsor_id: Optional[int] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=200),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if q:
        q = q.strip()
        filters.append(or_(Certificate.certificate_id.ilike(f"%{q}%"), Certificate.learner_name.ilike(f"%{q}%")))
    if access_type:
        filters.append(Certificate.access_type == access_type)
    if sponsor_id is not None:
        filters.append(Certificate.organization_id == sponsor_id)
    total = int((await db.execute(select(func.count(Certificate.id)).where(*filters))).scalar_one())
    rows = (await db.execute(
        select(Certificate).where(*filters).order_by(Certificate.issued_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [{**_cert_out(c), "user_id": c.user_id} for c in rows],
    }


async def _get_cert(db: AsyncSession, certificate_id: str) -> Certificate:
    cert = (await db.execute(
        select(Certificate).where(Certificate.certificate_id == certificate_id)
    )).scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert


@router.get("/certificates/{certificate_id}/pdf")
async def download_certificate(
    certificate_id: str,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """The PDF itself. Works for every certificate, including one still
    awaiting payment (admins support learners); that download is logged."""
    cert = await _get_cert(db, certificate_id)
    pdf = await certificate_files.pdf_bytes(db, settings, cert)
    audit.record(
        db, admin, "certificate.download", f"Downloaded certificate {cert.certificate_id} ({cert.learner_name})",
        target_type="certificate", target_id=cert.certificate_id, request=request,
    )
    await db.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{certificate_files.filename(cert)}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/certificates/{certificate_id}/link")
async def certificate_share_link(
    certificate_id: str,
    body: CertificateLinkRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """A link anyone can open (no login) until it expires — for sending a
    learner their certificate on Telegram, SMS or email."""
    cert = await _get_cert(db, certificate_id)
    if not cert.is_verified and not body.allow_unpaid:
        raise HTTPException(
            status_code=402,
            detail="This certificate is awaiting payment. Tick 'share anyway' to send it regardless.",
        )
    token = certificate_files.make_link_token(cert.certificate_id, body.days)
    expires_at = datetime.utcnow() + timedelta(days=max(1, min(body.days, certificate_files.LINK_DAYS_MAX)))
    audit.record(
        db, admin, "certificate.share_link",
        f"Made a {body.days}-day download link for {cert.certificate_id} ({cert.learner_name})",
        target_type="certificate", target_id=cert.certificate_id,
        details={"days": body.days, "unpaid": not cert.is_verified}, request=request,
    )
    await db.commit()
    return {
        "certificate_id": cert.certificate_id,
        "path": certificate_files.link_path(cert.certificate_id, token),
        "expires_at": expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# payments
# ---------------------------------------------------------------------------

@router.get("/payments")
async def list_payments(
    q: Optional[str] = Query(None, max_length=100, description="Reference, email or note"),
    purpose: Optional[str] = Query(None, max_length=30),
    status: Optional[str] = Query(None, max_length=20),
    sponsor_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if q:
        q = q.strip()
        filters.append(or_(Payment.reference.ilike(f"%{q}%"), Payment.email.ilike(f"%{q}%"), Payment.note.ilike(f"%{q}%")))
    if purpose == "sponsor":
        filters.append(Payment.purpose.in_(SPONSOR_PAYMENT_PURPOSES))
    elif purpose:
        filters.append(Payment.purpose == purpose)
    if status:
        filters.append(Payment.status == status)
    if sponsor_id is not None:
        filters.append(Payment.organization_id == sponsor_id)
    when = func.coalesce(Payment.paid_at, Payment.created_at)
    if date_from:
        filters.append(when >= date_from)
    if date_to:
        filters.append(when < date_to)

    total = int((await db.execute(select(func.count(Payment.id)).where(*filters))).scalar_one())
    by_status = {
        s: int(n or 0)
        for s, n in (await db.execute(
            select(Payment.status, func.sum(Payment.amount_kobo)).where(*filters).group_by(Payment.status)
        )).all()
    }
    rows = (await db.execute(
        select(Payment, Organization.name, User.name)
        .outerjoin(Organization, Organization.id == Payment.organization_id)
        .outerjoin(User, User.id == Payment.user_id)
        .where(*filters)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .offset(offset)
        .limit(limit)
    )).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "totals_kobo": by_status,
        "items": [_payment_out(p, org_name, user_name) for p, org_name, user_name in rows],
    }


@router.post("/payments/{reference}/void")
async def void_payment(
    reference: str,
    body: VoidPaymentRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reverse a bank transfer an admin recorded by mistake. Paystack
    payments are settled by Paystack and can't be voided here (refund them
    in the Paystack dashboard)."""
    payment = (await db.execute(select(Payment).where(Payment.reference == reference))).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.purpose != PaymentPurpose.SPONSOR_MANUAL.value:
        raise HTTPException(status_code=409, detail="Only manually recorded bank transfers can be voided")
    if payment.status != PaymentStatus.SUCCESS.value:
        raise HTTPException(status_code=409, detail="This payment is already voided")
    payment.status = PaymentStatus.VOIDED.value
    payment.note = f"VOIDED: {body.reason} | {payment.note or ''}"[:255]
    audit.record(
        db, admin, "payment.void", f"Voided bank transfer {payment.reference}: {body.reason}",
        target_type="payment", target_id=payment.reference,
        details={"amount_kobo": payment.amount_kobo, "organization_id": payment.organization_id, "reason": body.reason},
        request=request,
    )
    await db.commit()
    return {"reference": payment.reference, "status": payment.status}


# ---------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------

def _audit_out(a: AdminAuditLog) -> Dict[str, Any]:
    return {
        "id": a.id,
        "admin_user_id": a.admin_user_id,
        "admin": a.admin_label,
        "action": a.action,
        "target_type": a.target_type,
        "target_id": a.target_id,
        "summary": a.summary,
        "details": a.details,
        "ip_address": a.ip_address,
        "created_at": _iso(a.created_at),
    }


@router.get("/audit")
async def audit_log(
    q: Optional[str] = Query(None, max_length=100),
    action: Optional[str] = Query(None, max_length=60, description="Exact action or a prefix like 'sponsor.'"),
    target_type: Optional[str] = Query(None, max_length=30),
    target_id: Optional[str] = Query(None, max_length=100),
    admin_user_id: Optional[int] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if q:
        filters.append(or_(AdminAuditLog.summary.ilike(f"%{q.strip()}%"), AdminAuditLog.admin_label.ilike(f"%{q.strip()}%")))
    if action:
        filters.append(AdminAuditLog.action.startswith(action) if action.endswith(".") else AdminAuditLog.action == action)
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type)
    if target_id:
        filters.append(AdminAuditLog.target_id == target_id)
    if admin_user_id is not None:
        filters.append(AdminAuditLog.admin_user_id == admin_user_id)
    total = int((await db.execute(select(func.count(AdminAuditLog.id)).where(*filters))).scalar_one())
    rows = (await db.execute(
        select(AdminAuditLog).where(*filters)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .offset(offset).limit(limit)
    )).scalars().all()
    actions = [a for (a,) in (await db.execute(select(AdminAuditLog.action).distinct().order_by(AdminAuditLog.action))).all()]
    return {"total": total, "offset": offset, "limit": limit, "actions": actions, "items": [_audit_out(a) for a in rows]}
