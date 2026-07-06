"""
SMS Channel Handler for MNAIR Platform
Handles Termii SMS integration for fallback notifications
"""

from __future__ import annotations
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.config import Settings


class SMSProvider:
    """
    SMS provider interface for Termii API
    Sends simple text notifications for critical events
    """

    def __init__(self, settings: Settings):
        """
        Initialize SMS provider

        Args:
            settings: Application settings with Termii credentials
        """
        self.settings = settings
        self.api_key = settings.TERMII_API_KEY
        self.sender_id = settings.TERMII_SENDER_ID
        self.base_url = "https://api.ng.termii.com/api"

    async def send_sms(
        self,
        phone_number: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Send SMS via Termii API

        Args:
            phone_number: Recipient phone number
            message: SMS message content (max 160 chars)

        Returns:
            API response dict
        """
        if not self.api_key:
            # Development mode - just log
            print(f"[SMS DEV MODE] To {phone_number}: {message}")
            return {"status": "dev_mode", "message_id": "dev_123"}

        # Truncate message to 160 chars
        if len(message) > 160:
            message = message[:157] + "..."

        url = f"{self.base_url}/sms/send"

        payload = {
            "to": phone_number,
            "from": self.sender_id,
            "sms": message,
            "type": "plain",
            "channel": "generic",
            "api_key": self.api_key
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                print(f"[ERROR] SMS send failed: {e}")
                return {"status": "error", "error": str(e)}


class SMSNotifier:
    """
    High-level SMS notification service
    Sends formatted SMS for specific events
    """

    def __init__(self, db: AsyncSession, settings: Settings):
        """
        Initialize SMS notifier

        Args:
            db: Database session
            settings: Application settings
        """
        self.db = db
        self.settings = settings
        self.sms_provider = SMSProvider(settings)

    async def send_welcome_sms(self, user: User) -> bool:
        """
        Send welcome SMS to new user

        Args:
            user: User object

        Returns:
            True if sent successfully
        """
        message = (
            f"Welcome to Make Nigeria AI Ready! "
            f"Learn AI in 7 days. FREE certificate. "
            f"Dial *384*8080# or WhatsApp to start. - MNAIR"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_day_complete_sms(self, user: User, day: int) -> bool:
        """
        Send day completion SMS

        Args:
            user: User object
            day: Completed day number

        Returns:
            True if sent successfully
        """
        message = (
            f"Congratulations! Day {day} complete. "
            f"Only {7-day} days left! "
            f"Keep learning via *384*8080# - MNAIR"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_course_complete_sms(self, user: User) -> bool:
        """
        Send course completion SMS

        Args:
            user: User object

        Returns:
            True if sent successfully
        """
        host = self.settings.FRONTEND_URL.replace("https://", "").replace("http://", "")
        message = (
            f"MNAIR Course Complete! "
            f"Your certificate is ready. "
            f"Visit {host} to download. "
            f"Well done!"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_certificate_ready_sms(
        self,
        user: User,
        certificate_code: str
    ) -> bool:
        """
        Send certificate ready notification

        Args:
            user: User object
            certificate_code: Unique certificate verification code

        Returns:
            True if sent successfully
        """
        verify_url = f"{self.settings.FRONTEND_URL}/verify?code={certificate_code}"
        message = (
            f"Your MNAIR certificate is ready! "
            f"Code: {certificate_code}. "
            f"Download at {verify_url}"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_reminder_sms(self, user: User, days_inactive: int) -> bool:
        """
        Send inactivity reminder

        Args:
            user: User object
            days_inactive: Number of days user has been inactive

        Returns:
            True if sent successfully
        """
        message = (
            f"We miss you! You're on Day {user.current_day}/7. "
            f"Continue learning AI at *384*8080#. "
            f"It's FREE! - MNAIR"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_quiz_reminder_sms(self, user: User) -> bool:
        """
        Send quiz reminder

        Args:
            user: User object

        Returns:
            True if sent successfully
        """
        message = (
            f"Complete your quiz to unlock next lesson. "
            f"You can retry 3 times. "
            f"Dial *384*8080# now! - MNAIR"
        )

        result = await self.sms_provider.send_sms(user.phone_number, message)
        return result.get("status") != "error"

    async def send_bulk_announcement(
        self,
        message: str,
        language: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Send bulk SMS to all users (or filtered by language)

        Args:
            message: SMS content (max 160 chars)
            language: Optional language filter

        Returns:
            Dict with success/failure counts
        """
        # Build query
        query = select(User).where(User.is_active == True)
        if language:
            query = query.where(User.language == language)

        result = await self.db.execute(query)
        users = result.scalars().all()

        success_count = 0
        failure_count = 0

        for user in users:
            result = await self.sms_provider.send_sms(user.phone_number, message)
            if result.get("status") != "error":
                success_count += 1
            else:
                failure_count += 1

        return {
            "success": success_count,
            "failure": failure_count,
            "total": len(users)
        }
