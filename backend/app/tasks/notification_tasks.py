"""
Notification background tasks
Handles automated reminders, certificate generation, and learner engagement.

v2 (WhatsApp-free): every outbound message goes through NotificationRouter,
which prefers the free channels (Telegram Bot API, Web Push) and only falls
back to paid SMS when SMS_REMINDERS_ENABLED is explicitly true.
"""

from __future__ import annotations
from datetime import datetime, timedelta, date, timezone
import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

import redis.asyncio as redis_asyncio
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.reminder_log import ReminderLog
from app.channels.notify import NotificationRouter
from app.channels.sms import SMSNotifier
from app.certificates.generator import CertificateGenerator
from app.config import settings

logger = get_task_logger(__name__)

# Daily nudge band: a learner who went quiet 20-23 hours ago gets exactly one
# "pick up where you stopped" message. The band (not a point) is what makes
# an hourly task catch everyone; Redis SET NX dedupe keeps it to one nudge per
# inactivity episode. Kept from the WhatsApp era because "about a day" is the
# right cadence — the free channels just make it cost nothing.
DAILY_NUDGE_MIN_HOURS = 20
DAILY_NUDGE_MAX_HOURS = 23
DAILY_NUDGE_DEDUPE_TTL = 60 * 60 * 48  # one nudge per inactivity episode


def _aware(dt: datetime) -> datetime:
    """PostgreSQL returns aware datetimes for timestamptz columns; SQLite
    (tests) returns naive. Normalize before arithmetic."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 3/7/14-day inactivity reminders (daily)
# ---------------------------------------------------------------------------

@shared_task(name="app.tasks.notification_tasks.send_inactive_user_reminders")
def send_inactive_user_reminders():
    """
    Remind learners who have been inactive for exactly 3, 7 or 14 days.
    Free channels first; SMS only when SMS_REMINDERS_ENABLED. Runs daily 10 AM WAT.
    """
    try:
        logger.info("Starting inactive user reminder task")
        result = asyncio.run(_send_reminders_async())
        logger.info(
            f"Sent {result['sent']} reminders, {result['failed']} failed, "
            f"{result['skipped']} skipped, {result['unreachable']} unreachable"
        )
        return result
    except Exception as e:
        logger.error(f"Inactive user reminder task failed: {e}")
        raise


async def _send_reminders_async():
    async with AsyncSessionLocal() as db:
        router = NotificationRouter(db, settings)
        three_days_ago = datetime.utcnow() - timedelta(days=3)

        result = await db.execute(
            select(User).where(
                and_(
                    User.role == UserRole.LEARNER,
                    User.last_active_at < three_days_ago,
                    User.current_day >= 1,
                    User.current_day < 7,
                    User.is_active == True,  # noqa: E712
                    User.consent_given == True,  # noqa: E712
                )
            )
        )
        inactive_users = result.scalars().all()

        sent = failed = skipped = unreachable = 0
        now = datetime.now(timezone.utc)

        for user in inactive_users:
            try:
                days_inactive = (now - _aware(user.last_active_at)).days
                if days_inactive not in (3, 7, 14):
                    skipped += 1
                    continue

                days_left = max(7 - (user.completed_days or 0), 1)
                channel, ok = await router.send_reminder(user, days_left)
                if channel == "none":
                    unreachable += 1
                    continue
                if ok:
                    sent += 1
                else:
                    failed += 1
                db.add(ReminderLog(
                    user_id=user.id,
                    channel=channel,
                    status="sent" if ok else "failed",
                    current_day=user.current_day,
                ))
            except Exception as e:
                logger.error(f"Failed to send reminder to user {user.id}: {e}")
                failed += 1

        await db.commit()
        return {
            "status": "success",
            "total_inactive": len(inactive_users),
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "unreachable": unreachable,
        }


# ---------------------------------------------------------------------------
# ~1-day nudge over the free channels (hourly)
# ---------------------------------------------------------------------------

@shared_task(name="app.tasks.notification_tasks.send_daily_nudges")
def send_daily_nudges():
    """
    Nudge Telegram / web learners who went quiet 20-23 hours ago.

    Runs hourly. Redis SET NX dedupe keyed on the inactivity episode
    guarantees at most one nudge per drop-off even though the 3-hour band
    spans multiple hourly runs. Never uses SMS — this is the high-frequency
    reminder and must stay free.
    """
    try:
        logger.info("Starting daily nudge task")
        result = asyncio.run(_send_daily_nudges_async())
        logger.info(
            f"Nudges: {result['sent']} sent, {result['failed']} failed, "
            f"{result['skipped']} already nudged, {result['unreachable']} unreachable"
        )
        return result
    except Exception as e:
        logger.error(f"Daily nudge task failed: {e}")
        raise


async def _send_daily_nudges_async():
    now = datetime.utcnow()
    window_start = now - timedelta(hours=DAILY_NUDGE_MAX_HOURS)
    window_end = now - timedelta(hours=DAILY_NUDGE_MIN_HOURS)

    redis_client = redis_asyncio.from_url(settings.REDIS_URL)

    try:
        async with AsyncSessionLocal() as db:
            # SMS is deliberately disabled for this task regardless of config
            router = NotificationRouter(db, settings)
            router_settings = settings.model_copy(update={"SMS_REMINDERS_ENABLED": False})
            router.settings = router_settings

            result = await db.execute(
                select(User).where(
                    and_(
                        User.role == UserRole.LEARNER,
                        User.preferred_channel.in_(["telegram", "web"]),
                        User.is_active == True,  # noqa: E712
                        User.consent_given == True,  # noqa: E712
                        User.completed_days < 7,
                        User.last_active_at >= window_start,
                        User.last_active_at < window_end,
                    )
                )
            )
            eligible_users = result.scalars().all()

            sent = failed = skipped = unreachable = 0

            for user in eligible_users:
                try:
                    episode = int(_aware(user.last_active_at).timestamp())
                    dedupe_key = f"mnair:nudge:{user.id}:{episode}"

                    is_first = await redis_client.set(dedupe_key, "1", nx=True, ex=DAILY_NUDGE_DEDUPE_TTL)
                    if not is_first:
                        skipped += 1
                        continue

                    days_left = max(7 - (user.completed_days or 0), 1)
                    channel, ok = await router.send_reminder(user, days_left)

                    if channel == "none":
                        # Nothing to send through (e.g. web learner who never
                        # allowed notifications). Release the key so a later
                        # push subscription can still be nudged this episode.
                        await redis_client.delete(dedupe_key)
                        unreachable += 1
                        continue

                    if ok:
                        sent += 1
                    else:
                        await redis_client.delete(dedupe_key)  # retry next hour
                        failed += 1

                    db.add(ReminderLog(
                        user_id=user.id,
                        channel=channel,
                        status="sent" if ok else "failed",
                        current_day=user.current_day,
                    ))
                except Exception as e:
                    logger.error(f"Failed to nudge user {user.id}: {e}")
                    failed += 1

            await db.commit()
            return {
                "status": "success",
                "total_eligible": len(eligible_users),
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
                "unreachable": unreachable,
            }
    finally:
        await redis_client.close()


# ---------------------------------------------------------------------------
# Certificates (nightly)
# ---------------------------------------------------------------------------

@shared_task(name="app.tasks.notification_tasks.auto_generate_certificates")
def auto_generate_certificates():
    """
    Generate certificates for learners who completed Day 7 and confirmed a
    name, then tell them over their free channel. Runs daily at 2 AM WAT.
    """
    try:
        logger.info("Starting auto certificate generation task")
        result = asyncio.run(_generate_certificates_async())
        logger.info(
            f"Generated {result['generated']} certificates, "
            f"{result['failed']} failed, {result['already_exists']} already existed, "
            f"{result['notify_failed']} generated but not delivered on any channel"
        )
        return result
    except Exception as e:
        logger.error(f"Auto certificate generation failed: {e}")
        raise


async def _generate_certificates_async():
    async with AsyncSessionLocal() as db:
        generator = CertificateGenerator(db, settings)
        router = NotificationRouter(db, settings)

        # name_confirmed gates this: never generate a certificate carrying the
        # auto-assigned "Telegram User"/"Web Learner" placeholder.
        result = await db.execute(
            select(User).where(
                and_(
                    User.current_day >= 7,
                    User.is_active == True,  # noqa: E712
                    User.name_confirmed == True,  # noqa: E712
                )
            )
        )
        completed_users = result.scalars().all()

        generated = failed = already_exists = notify_failed = 0

        for user in completed_users:
            try:
                if await generator.get_user_certificate(user.id):
                    already_exists += 1
                    continue

                certificate = await generator.generate_and_store_certificate(
                    user_id=user.id, language=user.language
                )
                generated += 1

                channel, ok = await router.send_certificate_ready(user, certificate.certificate_id)
                if ok:
                    logger.info(
                        f"Generated certificate {certificate.certificate_id} for user {user.id} (via {channel})"
                    )
                else:
                    # Certificate exists and is retrievable from the verify
                    # page, but the learner was told nothing — flag it
                    # distinctly from a generation failure.
                    notify_failed += 1
                    logger.warning(
                        f"Certificate {certificate.certificate_id} generated for user {user.id} "
                        f"but not delivered (channel={channel})"
                    )
            except Exception as e:
                logger.error(f"Failed to generate certificate for user {user.id}: {e}")
                failed += 1

        return {
            "status": "success",
            "total_completed_users": len(completed_users),
            "generated": generated,
            "failed": failed,
            "already_exists": already_exists,
            "notify_failed": notify_failed,
        }


# ---------------------------------------------------------------------------
# Day-completion congratulations (USSD/SMS learners only, opt-in)
# ---------------------------------------------------------------------------

@shared_task(name="app.tasks.notification_tasks.send_quiz_reminders")
def send_quiz_reminders():
    """Placeholder — needs lesson_started_at tracking before it can be built."""
    logger.info("Quiz reminder task (MVP - not fully implemented)")
    return {"status": "success", "message": "Quiz reminder task placeholder"}


@shared_task(name="app.tasks.notification_tasks.send_day_completion_notifications")
def send_day_completion_notifications():
    """
    Congratulate learners who completed a day today. Telegram/web learners
    already see the celebration in-thread, so this only targets USSD/SMS
    learners and only when SMS_REMINDERS_ENABLED (it is a paid message).
    """
    try:
        logger.info("Day completion notification task")
        return asyncio.run(_send_day_completion_async())
    except Exception as e:
        logger.error(f"Day completion notification failed: {e}")
        raise


async def _send_day_completion_async():
    if not settings.SMS_REMINDERS_ENABLED:
        return {"status": "skipped", "reason": "SMS_REMINDERS_ENABLED is false"}

    async with AsyncSessionLocal() as db:
        from app.models.lesson_progress import LessonProgress
        from app.models.lesson import Lesson
        from sqlalchemy import func

        sms_notifier = SMSNotifier(db, settings)
        today_start = datetime.combine(date.today(), datetime.min.time())

        result = await db.execute(
            select(User).where(
                and_(
                    User.role == UserRole.LEARNER,
                    User.preferred_channel.in_(["ussd", "sms"]),
                    User.current_day >= 1,
                    User.current_day <= 7,
                    User.is_active == True,  # noqa: E712
                )
            )
        )
        users = result.scalars().all()

        notified = skipped = 0
        for user in users:
            try:
                lessons_result = await db.execute(
                    select(Lesson.id).where(and_(Lesson.day == user.current_day, Lesson.language == user.language))
                )
                lesson_ids = [row[0] for row in lessons_result]

                completed_today = (await db.execute(
                    select(func.count(LessonProgress.id)).where(
                        and_(
                            LessonProgress.user_id == user.id,
                            LessonProgress.lesson_id.in_(lesson_ids),
                            LessonProgress.is_completed == True,  # noqa: E712
                            LessonProgress.completed_at >= today_start,
                        )
                    )
                )).scalar() or 0

                if completed_today == 5:
                    await sms_notifier.send_day_complete_sms(user, user.current_day)
                    notified += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"Failed to check/notify user {user.id}: {e}")
                skipped += 1

        return {"status": "success", "users_checked": len(users), "notified": notified, "skipped": skipped}
