"""
Write admin audit rows. Call record() before the route's commit so the log
row and the change land in the same transaction: either both are saved or
neither is.
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AdminAuditLog
from app.models.user import User

# Never written into details, whatever a caller passes
_SECRET_KEYS = {"portal_password", "password", "pin", "hashed_password", "learner_pin_hash"}


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def _clean(details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not details:
        return None
    out: Dict[str, Any] = {}
    for key, value in details.items():
        if key in _SECRET_KEYS:
            out[key] = "(changed)"
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        elif hasattr(value, "value"):
            out[key] = value.value
        else:
            out[key] = value
    return out


def record(
    db: AsyncSession,
    admin: User,
    action: str,
    summary: str,
    *,
    target_type: Optional[str] = None,
    target_id: Any = None,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AdminAuditLog:
    row = AdminAuditLog(
        admin_user_id=admin.id,
        admin_label=(admin.name or admin.email or admin.phone_number or f"admin #{admin.id}")[:255],
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        summary=summary[:500],
        details=_clean(details),
        ip_address=_client_ip(request),
    )
    db.add(row)
    return row
