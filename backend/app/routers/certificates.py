"""
Certificate API endpoints
Handles certificate generation, retrieval, and verification
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.rate_limit import PUBLIC_RATE_LIMIT, limiter
from app.services import certificate_files
from app.models.user import User
from app.models.certificate import Certificate
from app.schemas.certificate import (
    CertificateResponse,
    CertificateVerification,
    CertificateGenerateRequest,
    CertificateDownloadResponse,
)
from app.utils.auth import get_current_user
from app.certificates.generator import CertificateGenerator

router = APIRouter(prefix="/api/v1/certificates", tags=["Certificates"])


@router.post("/generate", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def generate_certificate(
    request: Optional[CertificateGenerateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate certificate for user

    Requirements:
    - User must have completed all 7 days (current_day >= 7)
    - Certificate is generated only once (subsequent calls return existing certificate)

    Returns certificate metadata with MinIO PDF path
    """
    from app.config import settings

    # Determine user_id and language
    user_id = request.user_id if request and request.user_id else current_user.id
    language = request.language if request and request.language else current_user.language

    # If requesting for different user, require admin privileges
    if user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot generate certificate for another user"
        )

    # Get target user
    if user_id != current_user.id:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        target_user = result.scalar_one_or_none()

        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
    else:
        target_user = current_user

    # Check if user has completed the course
    if target_user.current_day < 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course not complete. User is on Day {target_user.current_day}/7"
        )

    # Generate certificate
    generator = CertificateGenerator(db, settings)

    try:
        certificate = await generator.generate_and_store_certificate(
            user_id=user_id,
            language=language
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return certificate


@router.get("/me", response_model=CertificateResponse)
async def get_my_certificate(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's certificate

    Returns 404 if certificate doesn't exist (user hasn't completed course)
    """
    from app.config import settings

    generator = CertificateGenerator(db, settings)
    certificate = await generator.get_user_certificate(current_user.id)

    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found. Complete the course first!"
        )

    return certificate


@router.get("/me/download", response_model=CertificateDownloadResponse)
async def get_my_certificate_download_url(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get download URL for current user's certificate

    Returns pre-signed MinIO URL valid for 7 days
    """
    from app.config import settings

    generator = CertificateGenerator(db, settings)
    certificate = await generator.get_user_certificate(current_user.id)

    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found. Complete the course first!"
        )

    if not certificate.is_verified:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Unlock your verified certificate to download it."
        )

    # Get pre-signed download URL
    download_url = await generator.get_certificate_url(certificate.certificate_id)

    if not download_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL. Please try again."
        )

    return CertificateDownloadResponse(
        certificate_id=certificate.certificate_id,
        download_url=download_url,
        expires_in_seconds=7 * 24 * 60 * 60,  # 7 days
        pdf_filename=certificate.pdf_filename
    )


@router.get("/file/{certificate_id}")
@limiter.limit(PUBLIC_RATE_LIMIT)
async def download_certificate_by_link(
    request: Request,
    certificate_id: str,
    t: str = Query(..., min_length=20, max_length=2000),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Certificate PDF behind a signed share link (made by an admin or the
    sponsor). The token names one certificate and expires on its own.
    """
    if certificate_files.certificate_id_from_token(t) != certificate_id:
        raise HTTPException(status_code=404, detail="This download link is invalid or has expired")
    cert = (await db.execute(
        select(Certificate).where(Certificate.certificate_id == certificate_id)
    )).scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="This download link is invalid or has expired")
    pdf = await certificate_files.pdf_bytes(db, settings, cert)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{certificate_files.filename(cert)}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/verify/{certificate_id}", response_model=CertificateVerification)
async def verify_certificate(
    certificate_id: str,
    name: str = Query(..., min_length=2, max_length=255, description="Full name printed on the certificate"),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify certificate authenticity (PUBLIC endpoint - no auth required)

    Requires both the certificate ID and the name printed on it. This is
    deliberate: a certificate code alone must never let a stranger pull out
    who it belongs to. The response never includes a phone number, and is
    identical (404) whether the code is unknown or the name doesn't match,
    so this endpoint can't be used to fish real names out of guessed codes.
    """
    from app.config import settings

    generator = CertificateGenerator(db, settings)
    verification_result = await generator.verify_certificate(certificate_id, name)

    if not verification_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found or name does not match"
        )

    return CertificateVerification(**verification_result)


@router.get("/user/{user_id}", response_model=CertificateResponse)
async def get_user_certificate(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get certificate for a specific user (Admin only)

    Requires admin privileges
    """
    # Only admins can view other users' certificates
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    from app.config import settings

    generator = CertificateGenerator(db, settings)
    certificate = await generator.get_user_certificate(user_id)

    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate not found for user {user_id}"
        )

    return certificate
