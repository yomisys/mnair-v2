"""
Analytics API endpoints
Provides KPI metrics and dashboard data for admin users
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    DashboardOverview,
    LanguageStats,
    DayStats,
    NetworkStats,
    TrendData,
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
