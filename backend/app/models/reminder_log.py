from __future__ import annotations

"""
ReminderLog model - Records every re-engagement nudge sent to learners
Powers the reminder analytics on the admin dashboard (sent counts,
failure counts, and re-engagement rate)
"""

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ReminderLog(Base):
    """
    One row per reminder attempt (WhatsApp window nudge or SMS reminder).
    Re-engagement is derived by comparing the user's last_active_at
    against sent_at — no extra write needed when the user comes back.
    """
    __tablename__ = "reminder_logs"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign Key
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Delivery details
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="whatsapp or sms"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="sent or failed"
    )

    # Learner position when the nudge went out (for funnel correlation)
    current_day: Mapped[int] = mapped_column(
        nullable=False,
        comment="User's current_day at send time"
    )

    # Timestamp
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Indexes for dashboard aggregation queries
    __table_args__ = (
        Index("idx_reminder_channel_status", "channel", "status"),
        Index("idx_reminder_sent_at_status", "sent_at", "status"),
    )

    def __repr__(self) -> str:
        return f"<ReminderLog user={self.user_id} {self.channel}/{self.status} at {self.sent_at}>"
