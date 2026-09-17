"""
Celery application configuration for MNAIR platform
Handles asynchronous and scheduled background tasks
"""

from __future__ import annotations
from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Create Celery app
celery_app = Celery(
    "mnair",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.analytics_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.maintenance_tasks",
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Lagos",  # Nigerian timezone (WAT - UTC+1)
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes max per task
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    # Daily analytics calculation - Run at 1 AM WAT every day
    "calculate-daily-analytics": {
        "task": "app.tasks.analytics_tasks.calculate_daily_analytics_task",
        "schedule": crontab(hour=1, minute=0),  # 1:00 AM WAT
    },

    # Send reminder to inactive users - Run at 10 AM WAT every day
    "send-inactive-user-reminders": {
        "task": "app.tasks.notification_tasks.send_inactive_user_reminders",
        "schedule": crontab(hour=10, minute=0),  # 10:00 AM WAT
    },

    # Free ~1-day nudge (Telegram / Web Push) for learners inactive 20-23h
    # - Run hourly at :15 to avoid on-the-hour pile-up
    "send-daily-nudges": {
        "task": "app.tasks.notification_tasks.send_daily_nudges",
        "schedule": crontab(minute=15),  # every hour at hh:15
    },

    # Auto-generate certificates for completed users - Run at 2 AM WAT
    "auto-generate-certificates": {
        "task": "app.tasks.notification_tasks.auto_generate_certificates",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM WAT
    },

    # Clean up old conversation data (NDPA compliance) - Run weekly on Sunday at 3 AM
    "cleanup-old-conversations": {
        "task": "app.tasks.maintenance_tasks.cleanup_old_conversations",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3:00 AM
    },

    # Database backup - Run daily at 4 AM WAT
    "backup-database": {
        "task": "app.tasks.maintenance_tasks.backup_database",
        "schedule": crontab(hour=4, minute=0),  # 4:00 AM WAT
    },
}

if __name__ == "__main__":
    celery_app.start()
