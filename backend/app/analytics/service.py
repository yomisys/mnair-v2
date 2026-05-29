"""
Analytics Service for MNAIR Platform
Calculates and aggregates KPIs for dashboard display
"""

from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import Analytics
from app.models.user import User
from app.models.lesson_progress import LessonProgress
from app.models.quiz_attempt import QuizAttempt
from app.models.certificate import Certificate
from app.models.employer import Employer


class AnalyticsService:
    """
    Service for calculating and aggregating platform analytics
    Generates daily snapshots of KPIs for dashboard
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize analytics service

        Args:
            db: Database session
        """
        self.db = db

    async def calculate_daily_analytics(self, target_date: Optional[date] = None) -> Analytics:
        """
        Calculate all analytics metrics for a specific date

        Args:
            target_date: Date to calculate analytics for (default: today)

        Returns:
            Analytics object with all calculated metrics
        """
        if target_date is None:
            target_date = date.today()

        # Check if analytics already exist for this date
        result = await self.db.execute(
            select(Analytics).where(Analytics.date == target_date)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            analytics = existing
        else:
            # Create new record
            analytics = Analytics(date=target_date)
            self.db.add(analytics)

        # Calculate all metrics
        await self._calculate_user_metrics(analytics, target_date)
        await self._calculate_completion_metrics(analytics, target_date)
        await self._calculate_lesson_metrics(analytics, target_date)
        await self._calculate_quiz_metrics(analytics, target_date)
        await self._calculate_channel_distribution(analytics)
        await self._calculate_language_distribution(analytics)
        await self._calculate_day_distribution(analytics)
        await self._calculate_certificate_metrics(analytics, target_date)
        await self._calculate_network_distribution(analytics)
        await self._calculate_employer_metrics(analytics, target_date)
        await self._calculate_top_lessons(analytics)

        # Update timestamp
        analytics.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(analytics)

        return analytics

    async def _calculate_user_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate user-related metrics"""
        # Total users
        total_result = await self.db.execute(select(func.count(User.id)))
        analytics.total_users = total_result.scalar() or 0

        # New users today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        new_users_result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.created_at >= start_of_day,
                    User.created_at <= end_of_day
                )
            )
        )
        analytics.new_users_today = new_users_result.scalar() or 0

        # Active users today
        active_today_result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.last_active_at >= start_of_day,
                    User.last_active_at <= end_of_day
                )
            )
        )
        analytics.active_users_today = active_today_result.scalar() or 0

        # Active users 7 days
        seven_days_ago = start_of_day - timedelta(days=7)
        active_7d_result = await self.db.execute(
            select(func.count(User.id)).where(
                User.last_active_at >= seven_days_ago
            )
        )
        analytics.active_users_7d = active_7d_result.scalar() or 0

        # Active users 30 days
        thirty_days_ago = start_of_day - timedelta(days=30)
        active_30d_result = await self.db.execute(
            select(func.count(User.id)).where(
                User.last_active_at >= thirty_days_ago
            )
        )
        analytics.active_users_30d = active_30d_result.scalar() or 0

    async def _calculate_completion_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate course completion metrics"""
        # Users in progress (days 1-6)
        in_progress_result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.current_day >= 1,
                    User.current_day < 7
                )
            )
        )
        analytics.users_in_progress = in_progress_result.scalar() or 0

        # Users completed (day 7+)
        completed_result = await self.db.execute(
            select(func.count(User.id)).where(User.current_day >= 7)
        )
        analytics.users_completed_program = completed_result.scalar() or 0

        # Completions today: lesson_progress rows marked complete today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        completions_today_result = await self.db.execute(
            select(func.count(LessonProgress.id)).where(
                and_(
                    LessonProgress.is_completed == True,
                    LessonProgress.completed_at >= start_of_day,
                    LessonProgress.completed_at <= end_of_day,
                )
            )
        )
        analytics.completions_today = completions_today_result.scalar() or 0

        # Completion rate
        if analytics.total_users > 0:
            analytics.completion_rate = (analytics.users_completed_program / analytics.total_users) * 100.0
        else:
            analytics.completion_rate = 0.0

    async def _calculate_lesson_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate lesson completion metrics"""
        # Total lessons completed
        total_lessons_result = await self.db.execute(
            select(func.count(LessonProgress.id)).where(
                LessonProgress.is_completed == True
            )
        )
        analytics.total_lessons_completed = total_lessons_result.scalar() or 0

        # Lessons completed today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        lessons_today_result = await self.db.execute(
            select(func.count(LessonProgress.id)).where(
                and_(
                    LessonProgress.is_completed == True,
                    LessonProgress.completed_at >= start_of_day,
                    LessonProgress.completed_at <= end_of_day
                )
            )
        )
        analytics.lessons_completed_today = lessons_today_result.scalar() or 0

        # Average lessons per user
        if analytics.total_users > 0:
            analytics.average_lessons_per_user = analytics.total_lessons_completed / analytics.total_users
        else:
            analytics.average_lessons_per_user = 0.0

    async def _calculate_quiz_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate quiz performance metrics"""
        # Total quiz attempts
        total_attempts_result = await self.db.execute(
            select(func.count(QuizAttempt.id))
        )
        analytics.total_quiz_attempts = total_attempts_result.scalar() or 0

        # Quiz attempts today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        attempts_today_result = await self.db.execute(
            select(func.count(QuizAttempt.id)).where(
                and_(
                    QuizAttempt.attempted_at >= start_of_day,
                    QuizAttempt.attempted_at <= end_of_day
                )
            )
        )
        analytics.quiz_attempts_today = attempts_today_result.scalar() or 0

        # Average quiz score
        avg_score_result = await self.db.execute(
            select(func.avg(QuizAttempt.score))
        )
        avg_score = avg_score_result.scalar()
        analytics.average_quiz_score = round(avg_score, 2) if avg_score else 0.0

        # Quiz pass rate (>= 60%)
        passed_result = await self.db.execute(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.score >= 60.0
            )
        )
        passed_count = passed_result.scalar() or 0

        if analytics.total_quiz_attempts > 0:
            analytics.quiz_pass_rate = (passed_count / analytics.total_quiz_attempts) * 100.0
        else:
            analytics.quiz_pass_rate = 0.0

    async def _calculate_channel_distribution(self, analytics: Analytics) -> None:
        """Calculate distribution of users by channel"""
        # For MVP, we'll just track by primary channel preference
        # In production, this would come from conversation/session data
        analytics.channel_distribution = {
            "whatsapp": 0,
            "ussd": 0,
            "sms": 0,
            "api": analytics.total_users  # Default to API for now
        }

    async def _calculate_language_distribution(self, analytics: Analytics) -> None:
        """Calculate distribution of users by language"""
        language_result = await self.db.execute(
            select(User.language, func.count(User.id))
            .group_by(User.language)
        )

        distribution = {}
        for lang, count in language_result:
            distribution[lang] = count

        analytics.language_distribution = distribution

    async def _calculate_day_distribution(self, analytics: Analytics) -> None:
        """Calculate distribution of users by current day"""
        day_result = await self.db.execute(
            select(User.current_day, func.count(User.id))
            .group_by(User.current_day)
        )

        distribution = {}
        for day, count in day_result:
            distribution[str(day)] = count

        analytics.day_distribution = distribution

    async def _calculate_certificate_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate certificate issuance metrics"""
        # Total certificates
        total_certs_result = await self.db.execute(
            select(func.count(Certificate.id))
        )
        analytics.certificates_issued = total_certs_result.scalar() or 0

        # Certificates issued today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        certs_today_result = await self.db.execute(
            select(func.count(Certificate.id)).where(
                and_(
                    Certificate.issued_at >= start_of_day,
                    Certificate.issued_at <= end_of_day
                )
            )
        )
        analytics.certificates_issued_today = certs_today_result.scalar() or 0

        # Certificates verified today (by employers)
        # This would need a verification_log table in production
        analytics.certificates_verified_today = 0

    async def _calculate_network_distribution(self, analytics: Analytics) -> None:
        """Calculate distribution by Nigerian telco operators"""
        # Extract network from phone number prefix
        # MTN: 0803, 0806, 0810, 0813, 0814, 0816, 0903, 0906, 0913, 0916
        # Glo: 0805, 0807, 0811, 0815, 0905, 0915
        # Airtel: 0802, 0808, 0812, 0901, 0902, 0904, 0907, 0912
        # 9mobile: 0809, 0817, 0818, 0909, 0908

        network_map = {
            "MTN": ["0803", "0806", "0810", "0813", "0814", "0816", "0903", "0906", "0913", "0916"],
            "Glo": ["0805", "0807", "0811", "0815", "0905", "0915"],
            "Airtel": ["0802", "0808", "0812", "0901", "0902", "0904", "0907", "0912"],
            "9mobile": ["0809", "0817", "0818", "0909", "0908"]
        }

        # Get all phone numbers
        users_result = await self.db.execute(
            select(User.phone_number)
        )
        phone_numbers = [row[0] for row in users_result]

        distribution = {"MTN": 0, "Glo": 0, "Airtel": 0, "9mobile": 0, "Unknown": 0}

        for phone in phone_numbers:
            # Normalize to 0XXX format
            if phone.startswith("+234"):
                phone = "0" + phone[4:]

            prefix = phone[:4]
            network_found = False

            for network, prefixes in network_map.items():
                if prefix in prefixes:
                    distribution[network] += 1
                    network_found = True
                    break

            if not network_found:
                distribution["Unknown"] += 1

        analytics.network_distribution = distribution

    async def _calculate_employer_metrics(self, analytics: Analytics, target_date: date) -> None:
        """Calculate employer registration metrics"""
        # Total employers
        total_employers_result = await self.db.execute(
            select(func.count(Employer.id))
        )
        analytics.total_employers = total_employers_result.scalar() or 0

        # New employers today
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        new_employers_result = await self.db.execute(
            select(func.count(Employer.id)).where(
                and_(
                    Employer.created_at >= start_of_day,
                    Employer.created_at <= end_of_day
                )
            )
        )
        analytics.new_employers_today = new_employers_result.scalar() or 0

    async def _calculate_top_lessons(self, analytics: Analytics) -> None:
        """Calculate top 10 most completed lessons"""
        top_lessons_result = await self.db.execute(
            select(
                LessonProgress.lesson_id,
                func.count(LessonProgress.id).label("completions")
            )
            .where(LessonProgress.is_completed == True)
            .group_by(LessonProgress.lesson_id)
            .order_by(func.count(LessonProgress.id).desc())
            .limit(10)
        )

        top_lessons = [
            {"lesson_id": lesson_id, "completions": completions}
            for lesson_id, completions in top_lessons_result
        ]

        analytics.top_lessons = top_lessons

    async def get_analytics_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[Analytics]:
        """
        Get analytics for a date range

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of Analytics objects ordered by date
        """
        result = await self.db.execute(
            select(Analytics)
            .where(
                and_(
                    Analytics.date >= start_date,
                    Analytics.date <= end_date
                )
            )
            .order_by(Analytics.date)
        )

        return list(result.scalars().all())

    async def get_latest_analytics(self) -> Optional[Analytics]:
        """
        Get the most recent analytics record

        Returns:
            Latest Analytics object or None
        """
        result = await self.db.execute(
            select(Analytics).order_by(Analytics.date.desc()).limit(1)
        )

        return result.scalar_one_or_none()
