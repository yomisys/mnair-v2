"""
Background tasks for MNAIR platform using Celery
Handles scheduled jobs: analytics, reminders, maintenance
"""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
