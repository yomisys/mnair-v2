from __future__ import annotations

"""
PushSubscription model - Web Push endpoints for web-app learners.

One row per browser/device that opted in to reminders on the web learner
app. Web Push is free (no per-message provider bill), which is why it
replaces WhatsApp template messages for reminders and certificate-ready
notices. Expired endpoints (410/404 from the push service) are deleted on
the next send attempt.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # PushSubscription.toJSON() fields from the browser
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)

    user_agent: Mapped[Optional[str]] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship("User", back_populates="push_subscriptions")

    __table_args__ = (
        Index("idx_push_user", "user_id"),
    )

    def as_webpush_dict(self) -> dict:
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}

    def __repr__(self) -> str:
        return f"<PushSubscription user={self.user_id} endpoint={self.endpoint[:40]}...>"
