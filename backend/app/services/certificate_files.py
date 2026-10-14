"""
Certificate PDFs for admins and sponsors: the bytes, and shareable links.

pdf_bytes() serves the issued PDF from MinIO when storage answers, and
otherwise re-renders it from the certificate record (same name, date, code
and sponsor credit). A storage outage therefore never blocks a download.

Share links are signed JWTs (sub "certfile:{certificate_id}") served by the
API itself, so they work without MinIO and expire on their own. They are
rejected by every login dependency: get_current_user needs an integer sub,
the sponsor and employer dependencies need their own prefixes.
"""

from __future__ import annotations
from datetime import timedelta
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.certificate import Certificate
from app.models.sponsor import Organization
from app.utils.auth import create_access_token

LINK_PREFIX = "certfile:"
LINK_DAYS_DEFAULT = 7
LINK_DAYS_MAX = 30


def _storage_client(settings: Settings):
    """MinIO client that gives up fast: a download should fall back to
    re-rendering in a few seconds, not hang on retries."""
    import urllib3
    from minio import Minio

    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=10), retries=False)
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        http_client=http,
    )


def _read_object(client, bucket: str, name: str) -> Optional[bytes]:
    response = None
    try:
        response = client.get_object(bucket, name)
        return response.read()
    except Exception:  # noqa: BLE001 -- any storage failure means "render instead"
        return None
    finally:
        if response is not None:
            response.close()
            response.release_conn()


async def pdf_bytes(db: AsyncSession, settings: Settings, cert: Certificate) -> bytes:
    from app.certificates.generator import CertificateGenerator

    client = _storage_client(settings)
    stored = _read_object(client, settings.MINIO_BUCKET, f"certificates/{cert.certificate_id}.pdf")
    if stored and stored.startswith(b"%PDF"):
        return stored

    logo = None
    if cert.organization_id:
        org = (await db.execute(
            select(Organization).where(Organization.id == cert.organization_id)
        )).scalar_one_or_none()
        if org and org.logo_object:
            logo = _read_object(client, settings.MINIO_BUCKET, org.logo_object)

    # create_certificate_pdf only draws; skip __init__, which talks to MinIO
    generator = CertificateGenerator.__new__(CertificateGenerator)
    generator.db, generator.settings, generator.minio_client = db, settings, client
    return generator.create_certificate_pdf(
        user_name=cert.learner_name,
        completion_date=cert.issued_at,
        verification_code=cert.certificate_id,
        language=cert.language or "en",
        sponsor_name=cert.sponsor_name,
        sponsor_logo=logo,
    )


def make_link_token(certificate_id: str, days: int = LINK_DAYS_DEFAULT) -> str:
    days = max(1, min(days, LINK_DAYS_MAX))
    return create_access_token(
        data={"sub": f"{LINK_PREFIX}{certificate_id}"},
        expires_delta=timedelta(days=days),
    )


def certificate_id_from_token(token: str) -> Optional[str]:
    # Same key create_access_token signs with
    from app.config import settings

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub") or ""
    if not sub.startswith(LINK_PREFIX):
        return None
    return sub[len(LINK_PREFIX):] or None


def link_path(certificate_id: str, token: str) -> str:
    return f"/api/v1/certificates/file/{certificate_id}?t={token}"


def filename(cert: Certificate) -> str:
    return f"MNAIR-certificate-{cert.certificate_id}.pdf"
