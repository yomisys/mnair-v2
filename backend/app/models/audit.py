"""
Admin audit log: one row per change an admin makes (sponsor edits, payments
recorded or voided, learner deactivated, PIN reset, certificate downloaded).

Rows are append-only. The admin's name is copied onto the row so the trail
still reads correctly after that admin account is deleted.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    admin_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    admin_label: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True, comment="e.g. sponsor.update")
    target_type: Mapped[Optional[str]] = mapped_column(String(30), comment="sponsor, code, learner, payment, certificate")
    target_id: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )

    __table_args__ = (
        Index("idx_audit_target", "target_type", "target_id"),
    )

    def __repr__(self) -> str:
        return f"<AdminAuditLog {self.action} {self.target_type}:{self.target_id}>"
