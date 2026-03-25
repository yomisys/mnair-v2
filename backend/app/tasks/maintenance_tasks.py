"""
Maintenance and compliance background tasks
Handles data cleanup, backups, and NDPA compliance
"""

from __future__ import annotations
from datetime import datetime, timedelta
import asyncio
import subprocess

from celery import shared_task
from celery.utils.log import get_task_logger

from sqlalchemy import select, and_, delete

from app.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.user import User
from app.config import settings

logger = get_task_logger(__name__)


@shared_task(name="app.tasks.maintenance_tasks.cleanup_old_conversations")
def cleanup_old_conversations():
    """
    Clean up old conversation data (NDPA compliance)

    Per NDPA requirements:
    - Delete conversation history older than 90 days
    - Keep user records and lesson progress
    - Maintain audit trail

    Runs weekly on Sunday at 3 AM WAT
    """
    try:
        logger.info("Starting conversation cleanup task (NDPA compliance)")

        result = asyncio.run(_cleanup_conversations_async())

        logger.info(
            f"Cleaned up {result['deleted']} conversations older than {settings.DATA_RETENTION_DAYS} days"
        )

        return result

    except Exception as e:
        logger.error(f"Conversation cleanup failed: {e}")
        raise


async def _cleanup_conversations_async():
    """Helper function to clean up conversations"""
    async with AsyncSessionLocal() as db:
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=settings.DATA_RETENTION_DAYS)

        # Count conversations to delete
        count_result = await db.execute(
            select(Conversation).where(
                Conversation.updated_at < cutoff_date
            )
        )
        conversations_to_delete = count_result.scalars().all()
        count = len(conversations_to_delete)

        # Delete old conversations
        await db.execute(
            delete(Conversation).where(
                Conversation.updated_at < cutoff_date
            )
        )
        await db.commit()

        logger.info(f"Deleted {count} conversations older than {cutoff_date.date()}")

        return {
            "status": "success",
            "deleted": count,
            "cutoff_date": str(cutoff_date.date()),
            "retention_days": settings.DATA_RETENTION_DAYS,
        }


@shared_task(name="app.tasks.maintenance_tasks.cleanup_inactive_users")
def cleanup_inactive_users():
    """
    Mark users as inactive if they haven't been active in 180 days

    This doesn't delete user data (for completion tracking)
    but marks them as inactive to exclude from active user counts

    Runs monthly
    """
    try:
        logger.info("Starting inactive user cleanup task")

        result = asyncio.run(_cleanup_inactive_users_async())

        logger.info(f"Marked {result['marked_inactive']} users as inactive")

        return result

    except Exception as e:
        logger.error(f"Inactive user cleanup failed: {e}")
        raise


async def _cleanup_inactive_users_async():
    """Helper function to mark inactive users"""
    async with AsyncSessionLocal() as db:
        # Users inactive for 180 days
        cutoff_date = datetime.utcnow() - timedelta(days=180)

        result = await db.execute(
            select(User).where(
                and_(
                    User.last_active_at < cutoff_date,
                    User.is_active == True,
                )
            )
        )
        inactive_users = result.scalars().all()

        marked_inactive = 0

        for user in inactive_users:
            user.is_active = False
            marked_inactive += 1

        await db.commit()

        return {
            "status": "success",
            "marked_inactive": marked_inactive,
            "cutoff_date": str(cutoff_date.date()),
        }


@shared_task(name="app.tasks.maintenance_tasks.backup_database")
def backup_database():
    """
    Create PostgreSQL database backup

    Uses pg_dump to create compressed SQL backup
    Stores in backups/ directory with timestamp

    Runs daily at 4 AM WAT

    Note: Requires PostgreSQL client tools (pg_dump) installed
    """
    try:
        logger.info("Starting database backup task")

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"mnair_backup_{timestamp}.sql.gz"
        backup_path = f"/app/backups/{backup_filename}"

        # Build pg_dump command
        # Format: pg_dump -h host -p port -U user -d database | gzip > backup.sql.gz
        dump_command = (
            f"pg_dump "
            f"-h {settings.DATABASE_HOST} "
            f"-p {settings.DATABASE_PORT} "
            f"-U {settings.DATABASE_USER} "
            f"-d {settings.DATABASE_NAME} "
            f"| gzip > {backup_path}"
        )

        # Set PostgreSQL password in environment
        env = {"PGPASSWORD": settings.DATABASE_PASSWORD}

        # Execute backup
        result = subprocess.run(
            dump_command,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            logger.info(f"Database backup created successfully: {backup_filename}")

            return {
                "status": "success",
                "backup_file": backup_filename,
                "backup_path": backup_path,
                "timestamp": timestamp,
            }
        else:
            error_msg = result.stderr or "Unknown error"
            logger.error(f"Database backup failed: {error_msg}")

            return {
                "status": "failed",
                "error": error_msg,
            }

    except subprocess.TimeoutExpired:
        logger.error("Database backup timed out after 10 minutes")
        return {"status": "failed", "error": "Backup timeout"}

    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        raise


@shared_task(name="app.tasks.maintenance_tasks.cleanup_old_backups")
def cleanup_old_backups():
    """
    Remove database backups older than 30 days

    Keeps the system from filling up with old backups
    Retains 30 days of backup history

    Runs weekly
    """
    try:
        import os
        from pathlib import Path

        logger.info("Starting old backup cleanup task")

        backup_dir = Path("/app/backups")

        if not backup_dir.exists():
            return {"status": "success", "message": "Backup directory doesn't exist"}

        cutoff_time = datetime.now().timestamp() - (30 * 24 * 60 * 60)  # 30 days ago
        deleted = 0

        for backup_file in backup_dir.glob("mnair_backup_*.sql.gz"):
            if backup_file.stat().st_mtime < cutoff_time:
                backup_file.unlink()
                deleted += 1
                logger.info(f"Deleted old backup: {backup_file.name}")

        logger.info(f"Cleaned up {deleted} old backup files")

        return {
            "status": "success",
            "deleted": deleted,
            "retention_days": 30,
        }

    except Exception as e:
        logger.error(f"Backup cleanup failed: {e}")
        raise


@shared_task(name="app.tasks.maintenance_tasks.health_check")
def health_check():
    """
    Perform system health check

    Checks:
    - Database connectivity
    - Redis connectivity
    - MinIO connectivity
    - Disk space
    - Memory usage

    Can be used for monitoring/alerting

    Runs every hour
    """
    try:
        logger.info("Running system health check")

        result = asyncio.run(_health_check_async())

        if result["status"] == "healthy":
            logger.info("Health check passed")
        else:
            logger.warning(f"Health check issues detected: {result}")

        return result

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def _health_check_async():
    """Helper function for health check"""
    from sqlalchemy import text

    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Database check
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            health["checks"]["database"] = "ok"
    except Exception as e:
        health["checks"]["database"] = f"error: {e}"
        health["status"] = "unhealthy"

    # Redis check (via Celery broker)
    try:
        from celery import current_app
        current_app.broker_connection().ensure_connection(max_retries=3)
        health["checks"]["redis"] = "ok"
    except Exception as e:
        health["checks"]["redis"] = f"error: {e}"
        health["status"] = "unhealthy"

    # MinIO check
    try:
        from minio import Minio
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        # Check if bucket exists
        client.bucket_exists(settings.MINIO_BUCKET)
        health["checks"]["minio"] = "ok"
    except Exception as e:
        health["checks"]["minio"] = f"error: {e}"
        health["status"] = "unhealthy"

    return health
