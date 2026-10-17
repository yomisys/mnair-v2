"""
Sponsors: the admin back office (create sponsors, codes, logos, payment
links, record bank transfers) and the sponsor portal (dashboard, learner
list, CSV export, monthly statement, pay deposit/balance).

Sponsor portal tokens carry sub "sponsor:{organization id}".
"""

import csv
import io
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.rate_limit import AUTH_RATE_LIMIT, PUBLIC_RATE_LIMIT, STRICT_RATE_LIMIT, limiter
from app.models.certificate import Certificate
from app.models.sponsor import CertificateAccess, Organization, Payment, PaymentPurpose, SponsorCode
from app.models.user import User
from app.schemas.admin import CertificateLinkRequest
from app.schemas.sponsor import (
    AdminPaymentLinkRequest,
    BrandingUpdate,
    CheckoutOut,
    CodeCreate,
    CodeOut,
    CodeUpdate,
    ManualPaymentRequest,
    OrganizationCreate,
    OrganizationUpdate,
    SponsorLogin,
    SponsorPayRequest,
)
from app.services import audit, certificate_files, sponsorship
from app.services.payments import record_manual_payment, start_sponsor_payment
from app.services.paystack import PaystackError
from app.utils.auth import (
    create_access_token,
    get_current_admin_user,
    get_current_sponsor,
    get_password_hash,
    verify_password,
)

LOGO_MAX_BYTES = 1024 * 1024
AD_IMAGE_MAX_BYTES = 2 * 1024 * 1024
LOGO_TYPES = {b"\x89PNG\r\n\x1a\n": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg")}

public_router = APIRouter(prefix="/api/v1/sponsors", tags=["Sponsors"])
portal_router = APIRouter(prefix="/api/v1/sponsors/me", tags=["Sponsor portal"])
admin_router = APIRouter(prefix="/api/v1/admin/sponsors", tags=["Admin: sponsors"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _code_out(code: SponsorCode, settings: Settings) -> CodeOut:
    username = (settings.TELEGRAM_BOT_USERNAME or "").lstrip("@")
    return CodeOut(
        id=code.id,
        code=code.code,
        label=code.label,
        max_enrolments=code.max_enrolments,
        expires_at=code.expires_at,
        is_active=code.is_active,
        join_url=f"{settings.learn_url}?code={code.code}",
        telegram_url=f"https://t.me/{username}?start={code.code}" if username else None,
    )


async def _get_org(db: AsyncSession, org_id: int) -> Organization:
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    return org


async def _new_code(db: AsyncSession, org: Organization, body: CodeCreate) -> SponsorCode:
    value = body.code
    if value is None:
        for _ in range(10):
            candidate = sponsorship.generate_code(org.name)
            if not (await db.execute(select(SponsorCode.id).where(SponsorCode.code == candidate))).first():
                value = candidate
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate a unique code")
    elif (await db.execute(select(SponsorCode.id).where(SponsorCode.code == value))).first():
        raise HTTPException(status_code=409, detail=f"Code {value} is already taken")
    code = SponsorCode(
        organization_id=org.id,
        code=value,
        label=body.label,
        max_enrolments=body.max_enrolments,
        expires_at=body.expires_at,
    )
    db.add(code)
    return code


async def _read_image(file: UploadFile, max_bytes: int, what: str):
    """PNG or JPEG under max_bytes. Checked by magic bytes and by actually
    decoding it, so a bad file fails here rather than on a certificate or a
    learner's screen. Returns (bytes, ext, content_type)."""
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{what} must be {max_bytes // (1024 * 1024)} MB or smaller")
    kind = next((v for sig, v in LOGO_TYPES.items() if content.startswith(sig)), None)
    if not kind:
        raise HTTPException(status_code=415, detail=f"{what} must be a PNG or JPEG image")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception:
        raise HTTPException(status_code=415, detail=f"{what} image could not be read")
    return content, kind[0], kind[1]


def _put_image(settings: Settings, folder: str, org: Organization, content: bytes, ext: str, content_type: str) -> str:
    object_name = f"{folder}/{org.id}-{int(datetime.utcnow().timestamp())}.{ext}"
    from minio import Minio
    try:
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        client.put_object(settings.MINIO_BUCKET, object_name, io.BytesIO(content), len(content), content_type=content_type)
    except Exception:
        raise HTTPException(status_code=503, detail="File storage unavailable — try again")
    return object_name


async def _live_code(db: AsyncSession, code: str):
    """(SponsorCode, Organization) for a code learners can join with, or 404."""
    value = sponsorship.normalize_code(code)
    row = (await db.execute(
        select(SponsorCode, Organization)
        .join(Organization, Organization.id == SponsorCode.organization_id)
        .where(SponsorCode.code == value)
    )).first()
    if not row or not row[0].is_active or not row[1].is_active:
        raise HTTPException(status_code=404, detail="Sponsor code not found")
    if row[0].expires_at and row[0].expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Sponsor code not found")
    return row[0], row[1]


def _month(year: Optional[int], month: Optional[int]):
    now = datetime.utcnow()
    year = year or now.year
    month = month or now.month
    if not (2024 <= year <= 2100 and 1 <= month <= 12):
        raise HTTPException(status_code=422, detail="Invalid period")
    return year, month


async def _checkout(db, settings, org, purpose: str, amount_kobo: Optional[int]) -> CheckoutOut:
    account = await sponsorship.account_summary(db, org)
    if amount_kobo is None:
        amount_kobo = account["deposit_outstanding_kobo"] if purpose == "deposit" else account["amount_due_kobo"]
    if amount_kobo <= 0:
        raise HTTPException(status_code=409, detail="Nothing to pay" if purpose == "balance" else "Deposit already paid")
    gateway_purpose = PaymentPurpose.SPONSOR_DEPOSIT.value if purpose == "deposit" else PaymentPurpose.SPONSOR_BALANCE.value
    try:
        payment = await start_sponsor_payment(db, settings, org, gateway_purpose, amount_kobo)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except PaystackError:
        raise HTTPException(status_code=503, detail="Payments are unavailable right now. Please try again later.")
    return CheckoutOut(
        reference=payment.reference,
        authorization_url=payment.authorization_url,
        amount_kobo=payment.amount_kobo,
        purpose=payment.purpose,
    )


def _payment_row(p: Payment) -> dict:
    return {
        "reference": p.reference,
        "purpose": p.purpose,
        "status": p.status,
        "amount_kobo": p.amount_kobo,
        "channel": p.channel,
        "note": p.note,
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _sponsored_cert(db: AsyncSession, org: Organization, certificate_id: str) -> Certificate:
    """A certificate this sponsor paid for, or 404 (never reveals others)."""
    cert = (await db.execute(
        select(Certificate).where(
            Certificate.certificate_id == certificate_id,
            Certificate.organization_id == org.id,
            Certificate.access_type == CertificateAccess.SPONSORED.value,
        )
    )).scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return cert


def _pdf_response(cert: Certificate, pdf: bytes, disposition: str = "attachment") -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{certificate_files.filename(cert)}"',
            "Cache-Control": "private, no-store",
        },
    )


def _csv_safe(value: str) -> str:
    """Learner names are free text: stop a name like '=HYPERLINK(...)' running
    as a formula when the sponsor opens the file in Excel."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _learners_csv(items) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "language", "current_day", "days_completed", "certified", "certificate_id", "joined_at", "last_active_at"])
    for i in items:
        writer.writerow([
            _csv_safe(i["name"]), i["language"], i["current_day"], i["completed_days"],
            "yes" if i["certified"] else "no", i["certificate_id"] or "", i["joined_at"] or "", i["last_active_at"] or "",
        ])
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mnair-learners.csv"},
    )


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

@public_router.get("/code/{code}")
@limiter.limit(PUBLIC_RATE_LIMIT)
async def lookup_code(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    """Name the sponsor behind a code, so the join page can say 'Sponsored
    by Grace Chapel' before the learner enrols. Reveals nothing else."""
    code_row, org = await _live_code(db, code)
    return {"code": code_row.code, "sponsor_name": org.name}


@public_router.get("/brand/{code}")
@limiter.limit(PUBLIC_RATE_LIMIT)
async def brand_for_code(
    request: Request, code: str, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
):
    """The white-label landing page (/s/<code>): sponsor name, colours,
    logo, welcome text, its advert, and the links to start learning."""
    code_row, org = await _live_code(db, code)
    links = _code_out(code_row, settings)
    return {
        "code": code_row.code,
        "join_url": links.join_url,
        "telegram_url": links.telegram_url,
        **sponsorship.public_brand(org),
    }


@public_router.get("/assets/{org_id}/{kind}")
async def brand_asset(
    org_id: int, kind: str, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
):
    """A sponsor's logo or advert image. Public on purpose: both are shown
    to learners and printed on certificates."""
    if kind not in ("logo", "ad_image"):
        raise HTTPException(status_code=404, detail="Not found")
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    name = (org.logo_object if kind == "logo" else org.ad_image_object) if org and org.is_active else None
    if not name:
        raise HTTPException(status_code=404, detail="Not found")
    content = certificate_files._read_object(certificate_files._storage_client(settings), settings.MINIO_BUCKET, name)
    if not content:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=content,
        media_type="image/png" if name.endswith(".png") else "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@public_router.post("/login")
@limiter.limit(AUTH_RATE_LIMIT)
async def sponsor_login(
    request: Request,
    body: SponsorLogin,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    org = (await db.execute(
        select(Organization).where(Organization.portal_email == body.email.lower())
    )).scalar_one_or_none()
    if not org or not org.hashed_password or not verify_password(body.password, org.hashed_password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    if not org.is_active:
        raise HTTPException(status_code=403, detail="Sponsor account is inactive")
    token = create_access_token(
        data={"sub": f"sponsor:{org.id}"},
        expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "organization": {"id": org.id, "name": org.name}}


# ---------------------------------------------------------------------------
# sponsor portal
# ---------------------------------------------------------------------------

@portal_router.get("/dashboard")
async def my_dashboard(
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    data = await sponsorship.dashboard(db, org)
    codes = (await db.execute(select(SponsorCode).where(SponsorCode.organization_id == org.id))).scalars().all()
    links = {c.code: _code_out(c, settings) for c in codes}
    for c in data["codes"]:
        c["join_url"] = links[c["code"]].join_url
        c["telegram_url"] = links[c["code"]].telegram_url
    data["payments_enabled"] = settings.payments_configured
    return data


@portal_router.get("/learners")
async def my_learners(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
):
    return await sponsorship.learner_list(db, org, offset, limit)


@portal_router.get("/learners.csv")
async def my_learners_csv(
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
):
    data = await sponsorship.learner_list(db, org, 0, 100_000)
    return _learners_csv(data["items"])


@portal_router.get("/statement")
async def my_statement(
    year: Optional[int] = None,
    month: Optional[int] = None,
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
):
    y, m = _month(year, month)
    return await sponsorship.monthly_statement(db, org, y, m)


@portal_router.get("/certificates/{certificate_id}/pdf")
async def my_certificate_pdf(
    certificate_id: str,
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """PDF of a certificate this sponsor paid for."""
    cert = await _sponsored_cert(db, org, certificate_id)
    return _pdf_response(cert, await certificate_files.pdf_bytes(db, settings, cert))


@portal_router.post("/certificates/{certificate_id}/link")
async def my_certificate_link(
    certificate_id: str,
    body: CertificateLinkRequest,
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
):
    """Shareable download link (no login needed) for a sponsored certificate."""
    cert = await _sponsored_cert(db, org, certificate_id)
    token = certificate_files.make_link_token(cert.certificate_id, body.days)
    return {
        "certificate_id": cert.certificate_id,
        "path": certificate_files.link_path(cert.certificate_id, token),
        "expires_at": (datetime.utcnow() + timedelta(days=body.days)).isoformat(),
    }


@portal_router.post("/pay", response_model=CheckoutOut)
@limiter.limit(STRICT_RATE_LIMIT)
async def my_pay(
    request: Request,
    body: SponsorPayRequest,
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Checkout for the outstanding deposit or the current amount due —
    the amount is always computed here, never taken from the client."""
    return await _checkout(db, settings, org, body.purpose, None)


@portal_router.get("/branding")
async def my_branding(org: Organization = Depends(get_current_sponsor)):
    return sponsorship.branding(org)


@portal_router.patch("/branding")
async def update_my_branding(
    body: BrandingUpdate,
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
):
    """The sponsor's landing page and advert. ad_suspended (the admin's
    override) is not in BrandingUpdate, so a sponsor cannot lift it."""
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "ad_enabled" and value is None:
            continue
        setattr(org, key, value)
    await db.commit()
    await db.refresh(org)
    return sponsorship.branding(org)


@portal_router.post("/branding/{kind}")
async def upload_my_brand_image(
    kind: str,
    file: UploadFile = File(...),
    org: Organization = Depends(get_current_sponsor),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """kind = logo (also printed on certificates, 1 MB) or ad_image (2 MB)."""
    if kind == "logo":
        content, ext, content_type = await _read_image(file, LOGO_MAX_BYTES, "Logo")
        org.logo_object = _put_image(settings, "sponsor-logos", org, content, ext, content_type)
    elif kind == "ad_image":
        content, ext, content_type = await _read_image(file, AD_IMAGE_MAX_BYTES, "Advert image")
        org.ad_image_object = _put_image(settings, "sponsor-ads", org, content, ext, content_type)
    else:
        raise HTTPException(status_code=404, detail="Not found")
    await db.commit()
    await db.refresh(org)
    return sponsorship.branding(org)


@portal_router.delete("/branding/ad_image")
async def remove_my_ad_image(org: Organization = Depends(get_current_sponsor), db: AsyncSession = Depends(get_db)):
    org.ad_image_object = None
    await db.commit()
    await db.refresh(org)
    return sponsorship.branding(org)


# ---------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------

@admin_router.get("")
async def list_sponsors(_: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    return await sponsorship.organization_list(db)


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_sponsor(
    body: OrganizationCreate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if body.portal_email and (await db.execute(
        select(Organization.id).where(Organization.portal_email == body.portal_email.lower())
    )).first():
        raise HTTPException(status_code=409, detail="That portal email is already in use")
    org = Organization(
        name=body.name.strip(),
        package=body.package.value,
        price_per_certificate_kobo=body.price_per_certificate_kobo,
        deposit_kobo=body.deposit_kobo,
        learner_cap=body.learner_cap,
        contact_email=body.contact_email,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        portal_email=body.portal_email.lower() if body.portal_email else None,
        hashed_password=get_password_hash(body.portal_password) if body.portal_password else None,
        notes=body.notes,
    )
    db.add(org)
    await db.flush()
    code = await _new_code(db, org, CodeCreate(code=body.first_code, label="Main code"))
    audit.record(
        db, admin, "sponsor.create", f"Created sponsor {org.name} ({org.package}) with code {code.code}",
        target_type="sponsor", target_id=org.id,
        details={
            "package": org.package, "price_per_certificate_kobo": org.price_per_certificate_kobo,
            "deposit_kobo": org.deposit_kobo, "learner_cap": org.learner_cap, "portal_login": bool(org.portal_email),
        },
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Code or portal email already in use")
    await db.refresh(org)
    await db.refresh(code)
    return {"id": org.id, "name": org.name, "code": _code_out(code, settings)}


@admin_router.patch("/{org_id}")
async def update_sponsor(
    org_id: int,
    body: OrganizationUpdate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org(db, org_id)
    before = {
        k: getattr(org, k) for k in (
            "name", "package", "contact_email", "contact_name", "contact_phone", "price_per_certificate_kobo",
            "deposit_kobo", "learner_cap", "is_active", "portal_email", "notes", "ad_suspended",
        )
    }
    data = body.model_dump(exclude_unset=True)
    password = data.pop("portal_password", None)
    if data.pop("clear_learner_cap", False):
        org.learner_cap = None
    if "package" in data and data["package"] is not None:
        data["package"] = data["package"].value
    if data.get("portal_email"):
        data["portal_email"] = data["portal_email"].lower()
        taken = (await db.execute(
            select(Organization.id).where(Organization.portal_email == data["portal_email"], Organization.id != org.id)
        )).first()
        if taken:
            raise HTTPException(status_code=409, detail="That portal email is already in use")
    for key, value in data.items():
        if value is not None or key in ("learner_cap", "contact_name", "contact_phone", "notes"):
            setattr(org, key, value)
    if password:
        org.hashed_password = get_password_hash(password)
    if org.hashed_password and not org.portal_email:
        raise HTTPException(status_code=422, detail="Set portal_email together with the password")
    changes = {
        k: {"from": v, "to": getattr(org, k)} for k, v in before.items() if getattr(org, k) != v
    }
    if password:
        changes["portal_password"] = "(changed)"
    if changes:
        action = "sponsor.update"
        if set(changes) == {"is_active"}:
            action = "sponsor.activate" if org.is_active else "sponsor.deactivate"
        elif set(changes) <= {"portal_password", "portal_email"}:
            action = "sponsor.portal_login"
        elif set(changes) == {"ad_suspended"}:
            action = "sponsor.advert_suspend" if org.ad_suspended else "sponsor.advert_restore"
        audit.record(
            db, admin, action, f"{org.name}: changed {', '.join(sorted(changes))}",
            target_type="sponsor", target_id=org.id, details=changes, request=request,
        )
    await db.commit()
    return {"id": org.id, "updated": sorted(list(data.keys()) + (["portal_password"] if password else []))}


@admin_router.get("/{org_id}/codes", response_model=List[CodeOut])
async def list_codes(
    org_id: int,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await _get_org(db, org_id)
    codes = (await db.execute(
        select(SponsorCode).where(SponsorCode.organization_id == org_id).order_by(SponsorCode.created_at)
    )).scalars().all()
    return [_code_out(c, settings) for c in codes]


@admin_router.post("/{org_id}/codes", response_model=CodeOut, status_code=status.HTTP_201_CREATED)
async def create_code(
    org_id: int,
    body: CodeCreate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    org = await _get_org(db, org_id)
    code = await _new_code(db, org, body)
    audit.record(
        db, admin, "code.create", f"{org.name}: new code {code.code}" + (f" ({code.label})" if code.label else ""),
        target_type="sponsor", target_id=org.id,
        details={"code": code.code, "label": code.label, "max_enrolments": code.max_enrolments, "expires_at": code.expires_at},
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Code already taken")
    await db.refresh(code)
    return _code_out(code, settings)


@admin_router.patch("/codes/{code_id}", response_model=CodeOut)
async def update_code(
    code_id: int,
    body: CodeUpdate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    code = (await db.execute(select(SponsorCode).where(SponsorCode.id == code_id))).scalar_one_or_none()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")
    changes = {}
    for key, value in body.model_dump(exclude_unset=True).items():
        if getattr(code, key) != value:
            changes[key] = {"from": getattr(code, key), "to": value}
        setattr(code, key, value)
    if changes:
        audit.record(
            db, admin, "code.update", f"Code {code.code}: changed {', '.join(sorted(changes))}",
            target_type="sponsor", target_id=code.organization_id, details={"code": code.code, **changes},
            request=request,
        )
    await db.commit()
    await db.refresh(code)
    return _code_out(code, settings)


@admin_router.post("/{org_id}/logo")
async def upload_logo(
    org_id: int,
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """PNG or JPEG, up to 1 MB. Checked by magic bytes and by actually
    decoding it, so a bad file fails here rather than on a certificate."""
    org = await _get_org(db, org_id)
    content, ext, content_type = await _read_image(file, LOGO_MAX_BYTES, "Logo")
    object_name = _put_image(settings, "sponsor-logos", org, content, ext, content_type)
    org.logo_object = object_name
    audit.record(
        db, admin, "sponsor.logo", f"{org.name}: uploaded a new logo", target_type="sponsor", target_id=org.id,
        request=request,
    )
    await db.commit()
    return {"id": org.id, "logo_object": object_name}


@admin_router.get("/{org_id}/dashboard")
async def sponsor_dashboard_admin(
    org_id: int, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
):
    return await sponsorship.dashboard(db, await _get_org(db, org_id))


@admin_router.get("/{org_id}/learners")
async def sponsor_learners_admin(
    org_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await sponsorship.learner_list(db, await _get_org(db, org_id), offset, limit, admin_view=True)


@admin_router.get("/{org_id}/learners.csv")
async def sponsor_learners_csv_admin(
    org_id: int, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
):
    data = await sponsorship.learner_list(db, await _get_org(db, org_id), 0, 100_000)
    return _learners_csv(data["items"])


@admin_router.get("/{org_id}/payments")
async def sponsor_payments_admin(
    org_id: int, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
):
    await _get_org(db, org_id)
    rows = (await db.execute(
        select(Payment).where(Payment.organization_id == org_id).order_by(Payment.created_at.desc(), Payment.id.desc())
    )).scalars().all()
    return [_payment_row(p) for p in rows]


@admin_router.get("/{org_id}")
async def sponsor_detail_admin(
    org_id: int,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Everything the sponsor page needs in one call: profile, account,
    progress, codes with links."""
    org = await _get_org(db, org_id)
    data = await sponsorship.dashboard(db, org)
    codes = (await db.execute(
        select(SponsorCode).where(SponsorCode.organization_id == org.id).order_by(SponsorCode.created_at)
    )).scalars().all()
    enrolled = {c["code"]: c["enrolled"] for c in data["codes"]}
    data["organization"].update({
        "is_active": org.is_active,
        "contact_name": org.contact_name,
        "contact_email": org.contact_email,
        "contact_phone": org.contact_phone,
        "portal_email": org.portal_email,
        "has_portal_password": bool(org.hashed_password),
        "notes": org.notes,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    })
    data["codes"] = [{**_code_out(c, settings).model_dump(mode="json"), "enrolled": enrolled.get(c.code, 0)} for c in codes]
    data["payments_enabled"] = settings.payments_configured
    return data


@admin_router.get("/{org_id}/statement")
async def sponsor_statement_admin(
    org_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    y, m = _month(year, month)
    return await sponsorship.monthly_statement(db, await _get_org(db, org_id), y, m)


@admin_router.post("/{org_id}/payment-link", response_model=CheckoutOut)
async def sponsor_payment_link(
    org_id: int,
    body: AdminPaymentLinkRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """A Paystack link to email to the sponsor (deposit or balance)."""
    org = await _get_org(db, org_id)
    # Added before _checkout, whose commit then saves it with the payment row
    audit.record(
        db, admin, "payment.link", f"{org.name}: Paystack {body.purpose} link",
        target_type="sponsor", target_id=org.id, details={"purpose": body.purpose, "amount_kobo": body.amount_kobo},
        request=request,
    )
    return await _checkout(db, settings, org, body.purpose, body.amount_kobo)


@admin_router.post("/{org_id}/manual-payment", status_code=status.HTTP_201_CREATED)
async def sponsor_manual_payment(
    org_id: int,
    body: ManualPaymentRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org(db, org_id)
    # record_manual_payment commits, saving this row with the payment
    audit.record(
        db, admin, "payment.manual", f"{org.name}: recorded bank transfer of NGN {body.amount_kobo / 100:,.2f}",
        target_type="sponsor", target_id=org.id, details={"amount_kobo": body.amount_kobo, "note": body.note},
        request=request,
    )
    payment = await record_manual_payment(db, org, body.amount_kobo, body.note, body.paid_at)
    return {"reference": payment.reference, "amount_kobo": payment.amount_kobo, "account": await sponsorship.account_summary(db, org)}


@admin_router.get("/payments/all")
async def list_payments(
    purpose: Optional[str] = None,
    status_: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Payment).order_by(Payment.created_at.desc()).limit(limit)
    if purpose:
        q = q.where(Payment.purpose == purpose)
    if status_:
        q = q.where(Payment.status == status_)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "reference": p.reference,
            "purpose": p.purpose,
            "status": p.status,
            "amount_kobo": p.amount_kobo,
            "organization_id": p.organization_id,
            "user_id": p.user_id,
            "channel": p.channel,
            "note": p.note,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]
