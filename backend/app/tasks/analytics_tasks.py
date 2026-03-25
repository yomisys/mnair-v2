"""
Analytics background tasks
Handles daily analytics calculations and aggregations
"""

from __future__ import annotations
from datetime import date, timedelta
import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

from app.database import AsyncSessionLocal
from app.analytics.service import AnalyticsService

logger = get_task_logger(__name__)


@shared_task(name="app.tasks.analytics_tasks.calculate_daily_analytics_task")
def calculate_daily_analytics_task(target_date: str = None):
    """
    Calculate daily analytics for a specific date

    Args:
        target_date: Date in YYYY-MM-DD format (default: yesterday)

    This task runs at 1 AM daily to calculate analytics for the previous day.
    Running at 1 AM ensures all data from previous day is captured.
    """
    try:
        # Parse target date
        if target_date:
            calc_date = date.fromisoformat(target_date)
        else:
            # Default to yesterday (since we run at 1 AM for previous day)
            calc_date = date.today() - timedelta(days=1)

        logger.info(f"Starting analytics calculation for {calc_date}")

        # Run async function in sync context
        result = asyncio.run(_calculate_analytics_async(calc_date))

        logger.info(
            f"Analytics calculated successfully for {calc_date}: "
            f"{result.total_users} users, "
            f"{result.lessons_completed_today} lessons completed"
        )

        return {
            "status": "success",
            "date": str(calc_date),
            "total_users": result.total_users,
            "new_users": result.new_users_today,
            "lessons_completed": result.lessons_completed_today,
        }

    except Exception as e:
        logger.error(f"Analytics calculation failed for {target_date}: {e}")
        raise


async def _calculate_analytics_async(target_date: date):
    """Helper function to run analytics calculation in async context"""
    async with AsyncSessionLocal() as db:
        service = AnalyticsService(db)
        analytics = await service.calculate_daily_analytics(target_date)
        return analytics


@shared_task(name="app.tasks.analytics_tasks.backfill_analytics")
def backfill_analytics(start_date: str, end_date: str):
    """
    Backfill analytics for a date range

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Useful for:
    - Initial setup
    - Fixing missing analytics data
    - Recalculating after data corrections
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if (end - start).days > 365:
            raise ValueError("Cannot backfill more than 365 days at once")

        logger.info(f"Starting analytics backfill from {start} to {end}")

        current_date = start
        results = []

        while current_date <= end:
            result = asyncio.run(_calculate_analytics_async(current_date))
            results.append({
                "date": str(current_date),
                "total_users": result.total_users,
            })
            logger.info(f"Backfilled analytics for {current_date}")
            current_date += timedelta(days=1)

        logger.info(f"Backfill completed: {len(results)} days processed")

        return {
            "status": "success",
            "days_processed": len(results),
            "start_date": start_date,
            "end_date": end_date,
        }

    except Exception as e:
        logger.error(f"Analytics backfill failed: {e}")
        raise


@shared_task(name="app.tasks.analytics_tasks.generate_weekly_report")
def generate_weekly_report():
    """
    Generate weekly summary report (Sunday night)

    Creates aggregated statistics for the past 7 days:
    - User growth
    - Completion trends
    - Quiz performance
    - Top lessons

    Could be used to:
    - Send email reports to admins
    - Post to Slack/Teams
    - Generate PDF reports
    """
    try:
        logger.info("Generating weekly analytics report")

        end_date = date.today()
        start_date = end_date - timedelta(days=7)

        result = asyncio.run(_generate_report_async(start_date, end_date))

        logger.info(
            f"Weekly report generated: {result['total_new_users']} new users, "
            f"{result['avg_completion_rate']:.1f}% completion rate"
        )

        return result

    except Exception as e:
        logger.error(f"Weekly report generation failed: {e}")
        raise


async def _generate_report_async(start_date: date, end_date: date):
    """Helper function to generate weekly report"""
    async with AsyncSessionLocal() as db:
        service = AnalyticsService(db)

        # Get analytics for date range
        analytics_list = await service.get_analytics_range(start_date, end_date)

        if not analytics_list:
            return {"status": "no_data"}

        # Calculate aggregates
        total_new_users = sum(a.new_users_today for a in analytics_list)
        total_completions = sum(a.completions_today for a in analytics_list)
        avg_completion_rate = sum(a.completion_rate for a in analytics_list) / len(analytics_list)
        avg_quiz_score = sum(a.average_quiz_score for a in analytics_list) / len(analytics_list)

        return {
            "status": "success",
            "period": f"{start_date} to {end_date}",
            "total_new_users": total_new_users,
            "total_completions": total_completions,
            "avg_completion_rate": round(avg_completion_rate, 2),
            "avg_quiz_score": round(avg_quiz_score, 2),
            "days_analyzed": len(analytics_list),
        }
