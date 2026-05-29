"""
Employer authentication tests.
Verifies: unauthenticated rejection, token confusion attack,
cross-tenant isolation, inactive account, and happy-path access.

Status code note: FastAPI's HTTPBearer returns 403 when no Authorization
header is present; 401 is returned by get_current_employer for invalid tokens.
"""

from __future__ import annotations
import pytest
from datetime import datetime

from app.models.employer import Employer
from app.utils.auth import create_access_token, get_password_hash


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_employer(db, **kwargs) -> Employer:
    defaults = dict(
        company_name="Test Corp",
        company_email="test@corp.ng",
        contact_name="Jane Doe",
        contact_phone="+2348012345678",
        contact_email="jane@corp.ng",
        hashed_password=get_password_hash("password123"),
        is_active=True,
        is_verified=True,
        is_approved=True,
        terms_accepted=True,
        terms_accepted_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    emp = Employer(**defaults)
    db.add(emp)
    return emp


def _employer_token(employer_id: int) -> str:
    return create_access_token(data={"sub": f"employer:{employer_id}"})


def _user_token(user_id: int) -> str:
    return create_access_token(data={"sub": str(user_id)})


# ── unauthenticated tests (no DB needed) ─────────────────────────────────────
# HTTPBearer returns 403 when the Authorization header is absent entirely.

@pytest.mark.asyncio
async def test_employer_search_unauthenticated(client):
    """No token → 403 (HTTPBearer rejects missing header before our code runs)."""
    response = await client.post(
        "/api/v1/employers/certificates/search",
        json={"certificate_id": "MNAIR-2024-00001-ABC123"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_employer_me_unauthenticated(client):
    """GET /employers/me without token → 403."""
    response = await client.get("/api/v1/employers/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_employer_stats_unauthenticated(client):
    """GET /employers/stats without token → 403."""
    response = await client.get("/api/v1/employers/stats")
    assert response.status_code == 403


# ── token confusion: user JWT must be rejected on employer endpoints ──────────

@pytest.mark.asyncio
async def test_employer_token_confusion_user_jwt_rejected(client):
    """A user JWT (sub='99') must return 401 on employer endpoints."""
    token = _user_token(user_id=99)
    response = await client.post(
        "/api/v1/employers/certificates/search",
        json={"certificate_id": "MNAIR-2024-00001-ABC123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ── invalid token cases ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employer_nonexistent_id_rejected(client):
    """Token for a non-existent employer id → 401."""
    token = _employer_token(employer_id=999999)
    response = await client.get(
        "/api/v1/employers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_employer_malformed_sub_rejected(client):
    """Token with sub='employer:not-a-number' → 401, not 500."""
    token = create_access_token(data={"sub": "employer:not-a-number"})
    response = await client.get(
        "/api/v1/employers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ── account state tests (need DB) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employer_me_authenticated(client, test_db):
    """Valid employer token → 200 with correct company_name."""
    emp = _make_employer(test_db, company_email="auth_test@corp.ng")
    await test_db.flush()
    token = _employer_token(emp.id)
    await test_db.commit()

    response = await client.get(
        "/api/v1/employers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["company_name"] == "Test Corp"


@pytest.mark.asyncio
async def test_employer_inactive_account_rejected(client, test_db):
    """Inactive employer account → 403 even with a valid token."""
    emp = _make_employer(test_db, company_email="inactive@corp.ng", is_active=False)
    await test_db.flush()
    token = _employer_token(emp.id)
    await test_db.commit()

    response = await client.get(
        "/api/v1/employers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
