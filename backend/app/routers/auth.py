"""
Authentication API endpoints
Handles user registration, login, and profile management
"""

from __future__ import annotations
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    UserResponse,
    ProgressSummary,
)
from app.utils.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_user,
)
from app.config import settings
from app.middleware.rate_limit import AUTH_RATE_LIMIT, DEFAULT_RATE_LIMIT

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user

    - **phone_number**: Nigerian phone number (will be normalized to +234 format)
    - **name**: Full name
    - **language**: Preferred language (en, pidgin, hausa, yoruba, igbo)
    - **consent_given**: Must be True (NDPA compliance)

    Returns user object and JWT token
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.phone_number == user_data.phone_number)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )

    # Create new user
    new_user = User(
        phone_number=user_data.phone_number,
        name=user_data.name,
        language=user_data.language,
        consent_given=user_data.consent_given,
        role="learner",  # Default role
        current_day=1,   # Start on day 1
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
async def login_user(
    request: Request,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login user with phone number

    For learners: Passwordless authentication
    For admins: Password required

    Returns JWT access token
    """
    # Find user by phone number
    result = await db.execute(
        select(User).where(User.phone_number == credentials.phone_number)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # For admin users, verify password
    if user.role == "admin":
        if not credentials.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password required for admin accounts"
            )

        # Admin users should have password_hash field
        if not hasattr(user, "hashed_password") or not user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Admin account not properly configured"
            )

        if not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password"
            )

    # Update last active timestamp
    from datetime import datetime
    user.last_active_at = datetime.utcnow()
    await db.commit()

    # Create JWT token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's profile

    Requires authentication (JWT token in Authorization header)
    """
    return current_user


@router.get("/me/progress", response_model=ProgressSummary)
async def get_user_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's progress summary

    Returns:
    - Current day (1-7)
    - Lessons completed
    - Total lessons (35)
    - Completion percentage
    - Average quiz score
    - Days active
    """
    from app.models.lesson_progress import LessonProgress
    from app.models.quiz_attempt import QuizAttempt
    from sqlalchemy import func

    # Count completed lessons
    completed_result = await db.execute(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == current_user.id,
            LessonProgress.is_completed == True
        )
    )
    lessons_completed = completed_result.scalar() or 0

    # Calculate average quiz score
    avg_score_result = await db.execute(
        select(func.avg(QuizAttempt.score)).where(
            QuizAttempt.user_id == current_user.id
        )
    )
    avg_score = avg_score_result.scalar()

    # Calculate days active (days since registration)
    from datetime import datetime
    days_active = (datetime.utcnow() - current_user.created_at).days + 1

    # Get last lesson date
    last_lesson_result = await db.execute(
        select(LessonProgress.completion_date).where(
            LessonProgress.user_id == current_user.id,
            LessonProgress.is_completed == True
        ).order_by(LessonProgress.completion_date.desc()).limit(1)
    )
    last_lesson_date = last_lesson_result.scalar_one_or_none()

    total_lessons = 35  # 7 days × 5 topics
    completion_percentage = (lessons_completed / total_lessons) * 100

    return ProgressSummary(
        user_id=current_user.id,
        current_day=current_user.current_day,
        lessons_completed=lessons_completed,
        total_lessons=total_lessons,
        completion_percentage=round(completion_percentage, 2),
        average_quiz_score=round(avg_score, 2) if avg_score else None,
        days_active=days_active,
        last_lesson_date=last_lesson_date
    )


@router.put("/me/language", response_model=UserResponse)
async def update_user_language(
    language: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user's preferred language

    Args:
        language: New language (en, pidgin, hausa, yoruba, igbo)
    """
    allowed_languages = ["en", "pidgin", "hausa", "yoruba", "igbo"]

    if language.lower() not in allowed_languages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid language. Must be one of: {', '.join(allowed_languages)}"
        )

    current_user.language = language.lower()
    await db.commit()
    await db.refresh(current_user)

    return current_user
