"""
Employer API endpoints
Handles employer registration, login, and certificate verification
"""

from __future__ import annotations
from datetime import timedelta, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employer import Employer
from app.models.certificate import Certificate
from app.models.user import User
from app.schemas.employer import (
    EmployerRegister,
    EmployerLogin,
    EmployerResponse,
    CertificateSearchRequest,
    CertificateSearchResult,
)
from app.schemas.auth import Token
from app.utils.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_employer,
)
from app.config import settings

router = APIRouter(prefix="/api/v1/employers", tags=["Employers"])


@router.post("/register", response_model=EmployerResponse, status_code=status.HTTP_201_CREATED)
async def register_employer(
    employer_data: EmployerRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new employer account

    Employers can verify certificates after:
    1. Email verification (automatic email sent)
    2. Admin approval (manual for MVP)

    Returns employer object
    """
    # Check if company email already exists
    result = await db.execute(
        select(Employer).where(Employer.company_email == employer_data.company_email)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company email already registered"
        )

    # Hash password
    hashed_password = get_password_hash(employer_data.password)

    # Create employer
    new_employer = Employer(
        company_name=employer_data.company_name,
        company_email=employer_data.company_email,
        contact_name=employer_data.contact_name,
        contact_phone=employer_data.contact_phone,
        contact_email=employer_data.contact_email,
        industry=employer_data.industry,
        company_size=employer_data.company_size,
        location=employer_data.location,
        website=employer_data.website,
        hashed_password=hashed_password,
        terms_accepted=employer_data.terms_accepted,
        terms_accepted_at=datetime.utcnow() if employer_data.terms_accepted else None,
        is_verified=False,  # Requires email verification
        is_approved=False,  # Requires admin approval
    )

    db.add(new_employer)
    await db.commit()
    await db.refresh(new_employer)

    return new_employer


@router.post("/login", response_model=Token)
async def login_employer(
    credentials: EmployerLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login employer and get JWT token

    Requires:
    - Valid email and password
    - Account must be active

    Returns JWT access token
    """
    # Find employer
    result = await db.execute(
        select(Employer).where(Employer.company_email == credentials.company_email)
    )
    employer = result.scalar_one_or_none()

    if not employer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer not found"
        )

    # Verify password
    if not verify_password(credentials.password, employer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )

    # Check if account is active
    if not employer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact support."
        )

    # Check if verified and approved
    if not employer.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Check your inbox."
        )

    if not employer.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending admin approval"
        )

    # Update last login
    employer.last_login_at = datetime.utcnow()
    await db.commit()

    # Create JWT token (use employer:id format to distinguish from users)
    access_token = create_access_token(
        data={"sub": f"employer:{employer.id}"},
        expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60
    )


@router.get("/me", response_model=EmployerResponse)
async def get_employer_profile(
    current_employer: Employer = Depends(get_current_employer),
    db: AsyncSession = Depends(get_db)
):
    """Get current employer's profile. Requires employer JWT."""
    return current_employer


@router.post("/certificates/search", response_model=List[CertificateSearchResult])
async def search_certificates(
    search: CertificateSearchRequest,
    current_employer: Employer = Depends(get_current_employer),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for certificates by phone number, name, or certificate ID

    Employers can search to verify learner credentials

    At least one search parameter required
    """
    if not any([search.phone_number, search.name, search.certificate_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one search parameter required"
        )

    # Build query
    query = select(Certificate).join(User, Certificate.user_id == User.id)

    filters = []
    if search.certificate_id:
        filters.append(Certificate.certificate_id == search.certificate_id)

    if search.phone_number:
        filters.append(Certificate.learner_phone == search.phone_number)

    if search.name:
        # Case-insensitive partial match
        filters.append(Certificate.learner_name.ilike(f"%{search.name}%"))

    if filters:
        query = query.where(or_(*filters))

    # Execute query
    result = await db.execute(query)
    certificates = result.scalars().all()

    # Convert to response
    results = []
    for cert in certificates:
        results.append(CertificateSearchResult(
            certificate_id=cert.certificate_id,
            learner_name=cert.learner_name,
            learner_phone=cert.learner_phone,
            issued_date=cert.issued_at,
            language=cert.language,
            average_quiz_score=cert.average_quiz_score,
            days_to_complete=cert.days_to_complete,
            completion_grade=cert.completion_grade,
            verification_hash=cert.verification_hash,
            verification_url=cert.verification_url
        ))

    current_employer.increment_verification_count()
    await db.commit()

    return results


@router.get("/certificates/verify/{certificate_id}", response_model=CertificateSearchResult)
async def verify_certificate_by_id(
    certificate_id: str,
    current_employer: Employer = Depends(get_current_employer),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a specific certificate by ID

    Returns certificate details if found and valid
    """
    result = await db.execute(
        select(Certificate).where(Certificate.certificate_id == certificate_id)
    )
    certificate = result.scalar_one_or_none()

    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found"
        )

    current_employer.increment_verification_count()
    await db.commit()

    return CertificateSearchResult(
        certificate_id=certificate.certificate_id,
        learner_name=certificate.learner_name,
        learner_phone=certificate.learner_phone,
        issued_date=certificate.issued_at,
        language=certificate.language,
        average_quiz_score=certificate.average_quiz_score,
        days_to_complete=certificate.days_to_complete,
        completion_grade=certificate.completion_grade,
        verification_hash=certificate.verification_hash,
        verification_url=certificate.verification_url
    )


@router.get("/stats", response_model=dict)
async def get_employer_stats(
    current_employer: Employer = Depends(get_current_employer),
    db: AsyncSession = Depends(get_db),
):
    """
    Get employer's verification statistics.
    Returns total certificates verified, this month, and last verification date.
    """
    return {
        "total_verified": current_employer.certificates_verified_count,
        "last_verification": current_employer.last_verification_at,
        "company_name": current_employer.company_name,
        "api_requests_count": current_employer.api_requests_count,
    }
