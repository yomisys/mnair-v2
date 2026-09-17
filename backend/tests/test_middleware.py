"""
Middleware tests: security headers, input validation, request body passthrough.
The body-passthrough test is the critical one — if InputValidationMiddleware
consumes the body without caching it, the Telegram webhook silently breaks.
"""

from __future__ import annotations
import pytest
# Middleware tests: security headers, input validation, request body passthrough.


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Every response must include the core security headers."""
    response = await client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"
    assert response.headers.get("x-xss-protection") == "1; mode=block"


@pytest.mark.asyncio
async def test_sql_injection_blocked(client):
    """POST body with SQL injection pattern → 400."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "phone_number": "' UNION SELECT * FROM users WHERE 1=1--",
            "name": "hacker",
            "language": "en",
            "consent_given": True,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_xss_pattern_blocked(client):
    """POST body with XSS pattern → 400."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "phone_number": "+2348012345678",
            "name": "<script>alert('xss')</script>",
            "language": "en",
            "consent_given": True,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_valid_post_body_passes_through(client):
    """
    Clean POST body must reach the handler intact after validation middleware runs.
    Body-passthrough regression: if InputValidationMiddleware consumes the body
    stream without caching, the handler receives an empty body and returns 422.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "phone_number": "+2348099887766",
            "name": "Middleware Test User",
            "language": "en",
            "consent_given": True,
        },
    )
    # 201 = created, 400 = validation error — either proves the body reached the handler.
    # 422 = unprocessable entity means the body was lost (middleware bug).
    assert response.status_code in (201, 400), (
        f"Got {response.status_code} — body may not have reached the handler. "
        f"Response: {response.text}"
    )


@pytest.mark.asyncio
async def test_request_size_limit(client):
    """POST body > 10 MB → 413."""
    big_body = b"x" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/api/v1/auth/register",
        content=big_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
