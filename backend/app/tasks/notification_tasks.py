"""
Notification background tasks
Handles automated reminders, certificate generation, and user engagement
"""

from __future__ import annotations
from datetime import datetime, timedelta, date
import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.certificate import Certificate
from app.channels.sms import SMSNotifier
from app.certificates.generator import CertificateGenerator
from app.config import settings

logger = get_task_logger(__name__)


@shared_task(name="app.tasks.notification_tasks.send_inactive_user_reminders")
def send_inactive_user_reminders():
    """
    Send SMS reminders to inactive users

    Targets users who:
    - Haven't been active in 3+ days
    - Are in progress (days 1-6)
    - Have given consent

    Runs daily at 10 AM WAT
    """
    try:
        logger.info("Starting inactive user reminder task")

        result = asyncio.run(_send_reminders_async())

        logger.info(
            f"Sent {result['sent']} reminders, {result['failed']} failed, "
            f"{result['skipped']} skipped"
        )

        return result

    except Exception as e:
        logger.error(f"Inactive user reminder task failed: {e}")
        raise


async def _send_reminders_async():
    """Helper function to send reminders"""
    async with AsyncSessionLocal() as db:
        sms_notifier = SMSNotifier(db, settings)

        # Find inactive users (no activity in 3 days, still in progress)
        three_days_ago = datetime.utcnow() - timedelta(days=3)

        result = await db.execute(
            select(User).where(
                and_(
                    User.last_active_at < three_days_ago,
                    User.current_day >= 1,
                    User.current_day < 7,
                    User.is_active == True,
                    User.consent_given == True,
                )
            )
        )
        inactive_users = result.scalars().all()

        sent = 0
        failed = 0
        skipped = 0

        for user in inactive_users:
            try:
                days_inactive = (datetime.utcnow() - user.last_active_at).days

                # Don't spam - only send if 3, 7, or 14 days inactive
                if days_inactive in [3, 7, 14]:
                    success = await sms_notifier.send_reminder_sms(user, days_inactive)
                    if success:
                        sent += 1
                    else:
                        failed += 1
                else:
                    skipped += 1

            except Exception as e:
                logger.error(f"Failed to send reminder to user {user.id}: {e}")
                failed += 1

        return {
            "status": "success",
            "total_inactive": len(inactive_users),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }


@shared_task(name="app.tasks.notification_tasks.auto_generate_certificates")
def auto_generate_certificates():
    """
    Automatically generate certificates for users who completed Day 7

    Checks for users who:
    - Are on day 7 or higher
    - Don't have a certificate yet
    - Are active accounts

    Runs daily at 2 AM WAT
    """
    try:
        logger.info("Starting auto certificate generation task")

        result = asyncio.run(_generate_certificates_async())

        logger.info(
            f"Generated {result['generated']} certificates, "
            f"{result['failed']} failed, {result['already_exists']} already existed"
        )

        return result

    except Exception as e:
        logger.error(f"Auto certificate generation failed: {e}")
        raise


async def _generate_certificates_async():
    """Helper function to generate certificates"""
    async with AsyncSessionLocal() as db:
        generator = CertificateGenerator(db, settings)
        sms_notifier = SMSNotifier(db, settings)

        # Find completed users without certificates
        result = await db.execute(
            select(User).where(
                and_(
                    User.current_day >= 7,
                    User.is_active == True,
                )
            )
        )
        completed_users = result.scalars().all()

        generated = 0
        failed = 0
        already_exists = 0

        for user in completed_users:
            try:
                # Check if certificate already exists
                existing_cert = await generator.get_user_certificate(user.id)

                if existing_cert:
                    already_exists += 1
                    continue

                # Generate certificate
                certificate = await generator.generate_and_store_certificate(
                    user_id=user.id,
                    language=user.language
                )

                # Send SMS notification
                await sms_notifier.send_certificate_ready_sms(
                    user,
                    certificate.certificate_id
                )

                generated += 1
                logger.info(f"Generated certificate {certificate.certificate_id} for user {user.id}")

            except Exception as e:
                logger.error(f"Failed to generate certificate for user {user.id}: {e}")
                failed += 1

        return {
            "status": "success",
            "total_completed_users": len(completed_users),
            "generated": generated,
            "failed": failed,
            "already_exists": already_exists,
        }


@shared_task(name="app.tasks.notification_tasks.send_quiz_reminders")
def send_quiz_reminders():
    """
    Send reminders to users who started a lesson but didn't complete the quiz

    This would require tracking lesson_started_at timestamp
    Currently simplified for MVP
    """
    try:
        logger.info("Quiz reminder task (MVP - not fully implemented)")

        # TODO: Implement quiz reminder logic when lesson_started_at tracking is added

        return {
            "status": "success",
            "message": "Quiz reminder task placeholder - implement with lesson start tracking"
        }

    except Exception as e:
        logger.error(f"Quiz reminder task failed: {e}")
        raise


@shared_task(name="app.tasks.notification_tasks.send_day_completion_notifications")
def send_day_completion_notifications():
    """
    Send congratulations SMS to users who completed a day today

    This task would:
    1. Find users who completed all 5 topics for their current day today
    2. Send congratulations SMS
    3. Encourage them to continue to next day

    Currently simplified for MVP
    """
    try:
        logger.info("Day completion notification task")

        result = asyncio.run(_send_day_completion_async())

        return result

    except Exception as e:
        logger.error(f"Day completion notification failed: {e}")
        raise


async def _send_day_completion_async():
    """Helper function to send day completion notifications"""
    async with AsyncSessionLocal() as db:
        from app.models.lesson_progress import LessonProgress
        from app.models.lesson import Lesson
        from sqlalchemy import func

        sms_notifier = SMSNotifier(db, settings)

        # Find users who might have completed a day today
        today_start = datetime.combine(date.today(), datetime.min.time())

        result = await db.execute(
            select(User).where(
                and_(
                    User.current_day >= 1,
                    User.current_day <= 7,
                    User.is_active == True,
                )
            )
        )
        users = result.scalars().all()

        notified = 0
        skipped = 0

        for user in users:
            try:
                # Count completed lessons for current day today
                lessons_result = await db.execute(
                    select(Lesson.id).where(
                        and_(
                            Lesson.day == user.current_day,
                            Lesson.language == user.language
                        )
                    )
                )
                lesson_ids = [row[0] for row in lessons_result]

                completed_today_result = await db.execute(
                    select(func.count(LessonProgress.id)).where(
                        and_(
                            LessonProgress.user_id == user.id,
                            LessonProgress.lesson_id.in_(lesson_ids),
                            LessonProgress.is_completed == True,
                            LessonProgress.completion_date >= today_start,
                        )
                    )
                )
                completed_today = completed_today_result.scalar() or 0

                # If completed all 5 topics today, send notification
                if completed_today == 5:
                    await sms_notifier.send_day_complete_sms(user, user.current_day)
                    notified += 1
                    logger.info(f"Sent day completion SMS to user {user.id} for day {user.current_day}")
                else:
                    skipped += 1

            except Exception as e:
                logger.error(f"Failed to check/notify user {user.id}: {e}")
                skipped += 1

        return {
            "status": "success",
            "users_checked": len(users),
            "notified": notified,
            "skipped": skipped,
        }
