"""
Analytics API endpoints
Provides KPI metrics and dashboard data for admin users
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, case, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt
from app.models.employer import Employer
from app.models.conversation import Conversation
from app.models.reminder_log import ReminderLog
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    DashboardOverview,
    LanguageStats,
    DayStats,
    NetworkStats,
    TrendData,
    LessonAnalytics,
    LanguagePerformance,
    EngagementFunnel,
    QuizLessonStats,
    ChannelPerformance,
    EmployerRecord,
    UserRecord,
    ReminderStats,
    ReminderChannelStats,
    ReminderDailyStats,
)
from app.utils.auth import get_current_admin_user
from app.analytics.service import AnalyticsService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get high-level analytics summary (Admin only)

    Returns key metrics:
    - Total users
    - Active users (7d)
    - Users completed
    - Completion rate
    - Average quiz score
    - Certificates issued
    - Total employers
    """
    service = AnalyticsService(db)

    # Get latest analytics
    analytics = await service.get_latest_analytics()

    if not analytics:
        # Generate analytics for today if none exist
        analytics = await service.calculate_daily_analytics()

    return AnalyticsSummary(
        total_users=analytics.total_users,
        active_users_7d=analytics.active_users_7d,
        users_completed_program=analytics.users_completed_program,
        completion_rate=analytics.completion_rate,
        average_quiz_score=analytics.average_quiz_score,
        certificates_issued=analytics.certificates_issued,
        total_employers=analytics.total_employers,
        user_retention_rate=analytics.user_retention_rate,
        daily_active_rate=analytics.daily_active_rate
    )


@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard_overview(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete dashboard overview with all metrics and distributions (Admin only)

    Includes:
    - Summary metrics
    - Language distribution
    - Day distribution
    - Network operator distribution
    - Growth trends (last 30 days)
    """
    service = AnalyticsService(db)

    # Get latest analytics
    analytics = await service.get_latest_analytics()

    if not analytics:
        analytics = await service.calculate_daily_analytics()

    # Build summary
    summary = AnalyticsSummary(
        total_users=analytics.total_users,
        active_users_7d=analytics.active_users_7d,
        users_completed_program=analytics.users_completed_program,
        completion_rate=analytics.completion_rate,
        average_quiz_score=analytics.average_quiz_score,
        certificates_issued=analytics.certificates_issued,
        total_employers=analytics.total_employers,
        user_retention_rate=analytics.user_retention_rate,
        daily_active_rate=analytics.daily_active_rate
    )

    # Language distribution
    language_stats = []
    for lang, count in analytics.language_distribution.items():
        percentage = analytics.get_language_percentage(lang)
        language_stats.append(LanguageStats(
            language=lang,
            user_count=count,
            percentage=round(percentage, 2)
        ))

    # Day distribution
    day_stats = []
    total_active_users = sum(analytics.day_distribution.values())
    for day_str, count in analytics.day_distribution.items():
        day = int(day_str)
        percentage = (count / total_active_users * 100) if total_active_users > 0 else 0
        day_stats.append(DayStats(
            day=day,
            user_count=count,
            percentage=round(percentage, 2)
        ))
    day_stats.sort(key=lambda x: x.day)

    # Network distribution
    network_stats = []
    for network, count in analytics.network_distribution.items():
        total_network_users = sum(analytics.network_distribution.values())
        percentage = (count / total_network_users * 100) if total_network_users > 0 else 0
        network_stats.append(NetworkStats(
            network=network,
            user_count=count,
            percentage=round(percentage, 2)
        ))

    # Get trends (last 30 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    historical = await service.get_analytics_range(start_date, end_date)

    user_growth_trend = [
        TrendData(
            date=a.date,
            value=float(a.total_users),
            label="Total Users"
        )
        for a in historical
    ]

    completion_trend = [
        TrendData(
            date=a.date,
            value=a.completion_rate,
            label="Completion Rate (%)"
        )
        for a in historical
    ]

    return DashboardOverview(
        summary=summary,
        language_distribution=language_stats,
        day_distribution=day_stats,
        network_distribution=network_stats,
        user_growth_trend=user_growth_trend,
        completion_trend=completion_trend,
        last_updated=analytics.updated_at
    )


@router.get("/daily/{target_date}", response_model=AnalyticsResponse)
async def get_daily_analytics(
    target_date: date,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get analytics for a specific date (Admin only)

    Args:
        target_date: Date in YYYY-MM-DD format

    Returns full analytics snapshot for that date
    """
    service = AnalyticsService(db)

    # Try to get existing analytics
    analytics_range = await service.get_analytics_range(target_date, target_date)

    if analytics_range:
        return analytics_range[0]
    else:
        # Calculate if doesn't exist
        analytics = await service.calculate_daily_analytics(target_date)
        return analytics


@router.get("/range", response_model=List[AnalyticsResponse])
async def get_analytics_range(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get analytics for a date range (Admin only)

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns list of analytics snapshots ordered by date
    """
    if (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 365 days"
        )

    service = AnalyticsService(db)
    analytics_list = await service.get_analytics_range(start_date, end_date)

    return analytics_list


@router.post("/calculate", response_model=AnalyticsResponse, status_code=status.HTTP_201_CREATED)
async def calculate_analytics(
    target_date: date = Query(None, description="Date to calculate (default: today)"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger analytics calculation for a date (Admin only)

    This recalculates all metrics and updates the database.
    Useful for backfilling or refreshing stale data.

    Args:
        target_date: Date to calculate (default: today)

    Returns newly calculated analytics
    """
    service = AnalyticsService(db)
    analytics = await service.calculate_daily_analytics(target_date)

    return analytics


@router.get("/lessons", response_model=List[LessonAnalytics])
async def get_lesson_analytics(
    language: Optional[str] = Query(None, description="Filter by language code"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Per-lesson completion rates and quiz performance (Admin only)"""
    q = (
        select(
            Lesson.lesson_id,
            Lesson.id.label("db_id"),
            Lesson.day,
            Lesson.topic,
            Lesson.language,
            Lesson.title,
            func.count(LessonProgress.id).label("started_count"),
            func.sum(case((LessonProgress.is_completed == True, 1), else_=0)).label("completed_count"),
            func.avg(LessonProgress.quiz_score).label("avg_score"),
            func.avg(LessonProgress.quiz_attempts_count).label("avg_attempts"),
            func.sum(
                case((and_(LessonProgress.quiz_attempts_count == 1, LessonProgress.is_completed == True), 1), else_=0)
            ).label("first_pass_count"),
        )
        .outerjoin(LessonProgress, Lesson.id == LessonProgress.lesson_id)
        .group_by(Lesson.id)
        .order_by(Lesson.day, Lesson.topic, Lesson.language)
    )
    if language:
        q = q.where(Lesson.language == language)

    rows = (await db.execute(q)).all()
    result = []
    for r in rows:
        started = r.started_count or 0
        completed = r.completed_count or 0
        first_pass = r.first_pass_count or 0
        result.append(LessonAnalytics(
            lesson_id=r.lesson_id,
            db_id=r.db_id,
            day=r.day,
            topic=r.topic,
            language=r.language,
            title=r.title,
            started_count=started,
            completed_count=completed,
            completion_rate=round((completed / started * 100) if started > 0 else 0, 1),
            avg_score=round(r.avg_score, 1) if r.avg_score is not None else None,
            avg_attempts=round(r.avg_attempts or 0, 2),
            first_attempt_pass_rate=round((first_pass / started * 100) if started > 0 else 0, 1),
        ))
    return result


@router.get("/languages", response_model=List[LanguagePerformance])
async def get_language_performance(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Completion rates and quiz scores broken down by language (Admin only)"""
    user_q = (
        select(
            User.language,
            func.count(User.id).label("total_users"),
            func.sum(case((User.completed_days >= 7, 1), else_=0)).label("completed_users"),
        )
        .where(User.is_active == True)
        .group_by(User.language)
    )
    user_rows = (await db.execute(user_q)).all()

    quiz_q = (
        select(
            User.language,
            func.avg(QuizAttempt.score).label("avg_score"),
        )
        .join(QuizAttempt, User.id == QuizAttempt.user_id)
        .group_by(User.language)
    )
    quiz_rows = {r.language: r.avg_score for r in (await db.execute(quiz_q)).all()}

    result = []
    for r in user_rows:
        total = r.total_users or 0
        completed = r.completed_users or 0
        dropout = round(((total - completed) / total * 100) if total > 0 else 0, 1)
        result.append(LanguagePerformance(
            language=r.language,
            total_users=total,
            completed_users=completed,
            completion_rate=round((completed / total * 100) if total > 0 else 0, 1),
            avg_quiz_score=round(quiz_rows.get(r.language, 0) or 0, 1),
            avg_days_to_complete=None,
            dropout_rate=dropout,
        ))
    result.sort(key=lambda x: x.total_users, reverse=True)
    return result


@router.get("/engagement", response_model=List[EngagementFunnel])
async def get_engagement_funnel(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Learner dropout funnel — how many users reach each day (Admin only)"""
    total_q = select(func.count(User.id)).where(User.is_active == True)
    total_users = (await db.execute(total_q)).scalar() or 0

    result = []
    prev_reached = total_users
    for day in range(1, 8):
        reached_q = (
            select(func.count(User.id))
            .where(and_(User.is_active == True, User.current_day >= day))
        )
        completed_day_q = (
            select(func.count(User.id))
            .where(and_(User.is_active == True, User.completed_days >= day))
        )
        reached = (await db.execute(reached_q)).scalar() or 0
        completed_day = (await db.execute(completed_day_q)).scalar() or 0
        dropoff = round(((prev_reached - reached) / prev_reached * 100) if prev_reached > 0 else 0, 1)
        cum_dropoff = round(((total_users - reached) / total_users * 100) if total_users > 0 else 0, 1)
        result.append(EngagementFunnel(
            day=day,
            users_reached=reached,
            users_completed_day=completed_day,
            dropoff_from_prev=dropoff,
            cumulative_dropoff=cum_dropoff,
        ))
        prev_reached = reached
    return result


@router.get("/quiz", response_model=List[QuizLessonStats])
async def get_quiz_analytics(
    language: Optional[str] = Query(None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Quiz retry patterns and score progression per lesson (Admin only)"""
    q = (
        select(
            Lesson.lesson_id,
            Lesson.id.label("db_id"),
            Lesson.day,
            Lesson.topic,
            Lesson.language,
            Lesson.title,
            func.count(QuizAttempt.id).label("total_attempts"),
            func.count(func.distinct(QuizAttempt.user_id)).label("unique_takers"),
            func.avg(case((QuizAttempt.passed == True, 1.0), else_=0.0)).label("pass_rate"),
            func.avg(QuizAttempt.score).label("avg_score"),
            func.avg(case((QuizAttempt.attempt_number == 1, QuizAttempt.score), else_=None)).label("avg_a1"),
            func.avg(case((QuizAttempt.attempt_number == 2, QuizAttempt.score), else_=None)).label("avg_a2"),
            func.avg(case((QuizAttempt.attempt_number == 3, QuizAttempt.score), else_=None)).label("avg_a3"),
        )
        .join(QuizAttempt, Lesson.id == QuizAttempt.lesson_id)
        .group_by(Lesson.id)
        .order_by(Lesson.day, Lesson.topic, Lesson.language)
    )
    if language:
        q = q.where(Lesson.language == language)

    rows = (await db.execute(q)).all()
    result = []
    for r in rows:
        unique = r.unique_takers or 0
        total = r.total_attempts or 0
        retried = total - unique
        retry_rate = round((retried / unique * 100) if unique > 0 else 0, 1)
        result.append(QuizLessonStats(
            lesson_id=r.lesson_id,
            db_id=r.db_id,
            day=r.day,
            topic=r.topic,
            language=r.language,
            title=r.title,
            total_attempts=total,
            unique_takers=unique,
            pass_rate=round((r.pass_rate or 0) * 100, 1),
            avg_score=round(r.avg_score or 0, 1),
            retry_rate=retry_rate,
            avg_score_attempt1=round(r.avg_a1, 1) if r.avg_a1 is not None else None,
            avg_score_attempt2=round(r.avg_a2, 1) if r.avg_a2 is not None else None,
            avg_score_attempt3=round(r.avg_a3, 1) if r.avg_a3 is not None else None,
        ))
    return result


@router.get("/channels", response_model=List[ChannelPerformance])
async def get_channel_performance(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Performance breakdown by delivery channel (Admin only)"""
    q = (
        select(
            func.coalesce(LessonProgress.channel_used, "unknown").label("channel"),
            func.count(func.distinct(LessonProgress.user_id)).label("unique_users"),
            func.count(LessonProgress.id).label("lesson_starts"),
            func.sum(case((LessonProgress.is_completed == True, 1), else_=0)).label("lesson_completions"),
            func.avg(LessonProgress.quiz_score).label("avg_score"),
        )
        .group_by(text("channel"))
        .order_by(func.count(LessonProgress.id).desc())
    )
    rows = (await db.execute(q)).all()
    result = []
    for r in rows:
        starts = r.lesson_starts or 0
        completions = r.lesson_completions or 0
        result.append(ChannelPerformance(
            channel=r.channel,
            unique_users=r.unique_users or 0,
            lesson_starts=starts,
            lesson_completions=completions,
            completion_rate=round((completions / starts * 100) if starts > 0 else 0, 1),
            avg_score=round(r.avg_score, 1) if r.avg_score is not None else None,
        ))
    return result


@router.get("/reminders", response_model=ReminderStats)
async def get_reminder_analytics(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Re-engagement nudge analytics (Admin only)

    A nudge counts as re-engaged when the user's last_active_at is later
    than the nudge's sent_at — i.e. they came back after we reminded them.
    """
    since = datetime.utcnow() - timedelta(days=days)

    re_engaged_case = case(
        (
            and_(
                ReminderLog.status == "sent",
                User.last_active_at.isnot(None),
                User.last_active_at > ReminderLog.sent_at,
            ),
            1,
        ),
        else_=0,
    )
    sent_case = case((ReminderLog.status == "sent", 1), else_=0)
    failed_case = case((ReminderLog.status == "failed", 1), else_=0)

    # Daily series
    day_col = func.date(ReminderLog.sent_at)
    daily_rows = (await db.execute(
        select(
            day_col.label("day"),
            func.sum(sent_case).label("sent"),
            func.sum(failed_case).label("failed"),
            func.sum(re_engaged_case).label("re_engaged"),
        )
        .join(User, ReminderLog.user_id == User.id)
        .where(ReminderLog.sent_at >= since)
        .group_by(day_col)
        .order_by(day_col)
    )).all()

    daily = [
        ReminderDailyStats(
            date=r.day,
            sent=r.sent or 0,
            failed=r.failed or 0,
            re_engaged=r.re_engaged or 0,
        )
        for r in daily_rows
    ]

    # Channel breakdown
    channel_rows = (await db.execute(
        select(
            ReminderLog.channel,
            func.sum(sent_case).label("sent"),
            func.sum(failed_case).label("failed"),
            func.sum(re_engaged_case).label("re_engaged"),
        )
        .join(User, ReminderLog.user_id == User.id)
        .where(ReminderLog.sent_at >= since)
        .group_by(ReminderLog.channel)
        .order_by(ReminderLog.channel)
    )).all()

    by_channel = []
    for r in channel_rows:
        sent = r.sent or 0
        re_engaged = r.re_engaged or 0
        by_channel.append(ReminderChannelStats(
            channel=r.channel,
            sent=sent,
            failed=r.failed or 0,
            re_engaged=re_engaged,
            re_engagement_rate=round((re_engaged / sent * 100) if sent > 0 else 0, 1),
        ))

    total_sent = sum(c.sent for c in by_channel)
    total_failed = sum(c.failed for c in by_channel)
    total_re_engaged = sum(c.re_engaged for c in by_channel)

    return ReminderStats(
        window_days=days,
        total_sent=total_sent,
        total_failed=total_failed,
        total_re_engaged=total_re_engaged,
        re_engagement_rate=round((total_re_engaged / total_sent * 100) if total_sent > 0 else 0, 1),
        by_channel=by_channel,
        daily=daily,
    )


@router.get("/employers", response_model=List[EmployerRecord])
async def get_employer_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Employer directory with verification activity (Admin only)"""
    q = select(Employer).order_by(Employer.certificates_verified_count.desc())
    rows = (await db.execute(q)).scalars().all()
    return [
        EmployerRecord(
            id=e.id,
            company_name=e.company_name,
            industry=e.industry,
            location=e.location,
            company_size=e.company_size,
            certificates_verified=e.certificates_verified_count,
            api_requests=e.api_requests_count,
            is_active=e.is_active,
            is_approved=e.is_approved,
            is_verified=e.is_verified,
            created_at=e.created_at,
            last_verification_at=e.last_verification_at,
        )
        for e in rows
    ]


@router.get("/users", response_model=List[UserRecord])
async def get_users_list(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """All registered learners with their progress and session counts (Admin only)"""
    q = (
        select(
            User.id,
            User.phone_number,
            User.name,
            User.language,
            User.role,
            User.current_day,
            User.completed_days,
            User.is_active,
            User.created_at,
            func.count(LessonProgress.id.distinct()).label("lesson_count"),
            func.count(QuizAttempt.id.distinct()).label("quiz_count"),
            func.count(Conversation.id.distinct()).label("conversation_count"),
        )
        .outerjoin(LessonProgress, User.id == LessonProgress.user_id)
        .outerjoin(QuizAttempt, User.id == QuizAttempt.user_id)
        .outerjoin(Conversation, User.id == Conversation.user_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = (await db.execute(q)).all()
    return [
        UserRecord(
            id=r.id,
            phone_number=r.phone_number,
            name=r.name,
            language=r.language,
            role=r.role,
            current_day=r.current_day,
            completed_days=r.completed_days,
            is_active=r.is_active,
            created_at=r.created_at,
            lesson_count=r.lesson_count or 0,
            quiz_count=r.quiz_count or 0,
            conversation_count=r.conversation_count or 0,
        )
        for r in rows
    ]
