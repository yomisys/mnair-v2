"""
Web learner API tests (/api/v1/learn): enrol, PIN login, turns, state
restore, push subscriptions, erasure.
"""

import pytest
from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.models.user import User
from tests.test_engine_flow import seed_days


PHONE = "08031234567"


async def enrol(client, phone=PHONE, pin="2468", **extra):
    r = await client.post("/api/v1/learn/enrol", json={"phone_number": phone, "pin": pin, "consent_given": True, **extra})
    return r


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_config_is_public(client):
    r = await client.get("/api/v1/learn/config")
    assert r.status_code == 200
    body = r.json()
    assert body["ussd_code"].startswith("*")
    assert "telegram_link" in body and "vapid_public_key" in body


@pytest.mark.asyncio
async def test_enrol_returns_token_and_welcome(client, test_db):
    await seed_days(test_db)
    r = await enrol(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    assert body["state"] == "awaiting_language"
    assert [m["kind"] for m in body["messages"]] == ["text", "choice"]
    assert body["learner"]["preferred_channel"] == "web"

    user = (await test_db.execute(select(User).where(User.phone_number == "+2348031234567"))).scalar_one()
    assert user.learner_pin_hash and user.learner_pin_hash != "2468"
    assert user.network_operator == "MTN"
    assert user.consent_given


@pytest.mark.asyncio
async def test_enrol_validation(client):
    r = await client.post("/api/v1/learn/enrol", json={"phone_number": "12345", "pin": "2468", "consent_given": True})
    assert r.status_code == 422
    r = await client.post("/api/v1/learn/enrol", json={"phone_number": PHONE, "pin": "ab12", "consent_given": True})
    assert r.status_code == 422
    r = await client.post("/api/v1/learn/enrol", json={"phone_number": PHONE, "pin": "2468", "consent_given": False})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_enrol_twice_conflicts_and_login_works(client, test_db):
    await seed_days(test_db)
    assert (await enrol(client)).status_code == 201
    assert (await enrol(client, phone="+2348031234567")).status_code == 409

    r = await client.post("/api/v1/learn/login", json={"phone_number": "2348031234567", "pin": "0000"})
    assert r.status_code == 401
    r = await client.post("/api/v1/learn/login", json={"phone_number": "2348031234567", "pin": "2468"})
    assert r.status_code == 200
    assert r.json()["messages"] == []  # thread already started; state restores via /state


@pytest.mark.asyncio
async def test_login_unknown_number_is_indistinguishable_from_wrong_pin(client):
    r = await client.post("/api/v1/learn/login", json={"phone_number": "08099999999", "pin": "1234"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Phone number or PIN is incorrect"


@pytest.mark.asyncio
async def test_legacy_ussd_learner_claims_pin_on_first_web_login(client, test_db):
    await seed_days(test_db)
    test_db.add(User(phone_number="+2348051112222", name="USSD User 2222", preferred_channel="ussd", consent_given=True))
    await test_db.commit()

    r = await client.post("/api/v1/learn/login", json={"phone_number": "08051112222", "pin": "9"})
    assert r.status_code == 422  # too short to claim
    r = await client.post("/api/v1/learn/login", json={"phone_number": "08051112222", "pin": "7777"})
    assert r.status_code == 200
    assert [m["kind"] for m in r.json()["messages"]] == ["text", "choice"]  # web thread kicked off
    assert r.json()["learner"]["preferred_channel"] == "web"

    r = await client.post("/api/v1/learn/login", json={"phone_number": "08051112222", "pin": "1111"})
    assert r.status_code == 401  # PIN now locked in


@pytest.mark.asyncio
async def test_turns_and_state_restore(client, test_db):
    await seed_days(test_db)
    token = (await enrol(client)).json()["access_token"]

    r = await client.post("/api/v1/learn/message", json={}, headers=auth(token))
    assert r.status_code == 422

    r = await client.post("/api/v1/learn/message", json={"interactive_id": "lang_en"}, headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "in_lesson"
    assert body["messages"][0]["kind"] == "lesson"
    assert body["progress"]["current_day"] == 1

    r = await client.post("/api/v1/learn/message", json={"text": "quiz"}, headers=auth(token))
    assert r.json()["messages"][0]["kind"] == "quiz"

    r = await client.get("/api/v1/learn/state", headers=auth(token))
    assert r.status_code == 200
    state = r.json()
    assert state["state"] == "awaiting_quiz"
    roles = [h["role"] for h in state["history"]]
    assert roles[:3] == ["user", "bot", "bot"]
    assert state["history"][-1]["kind"] == "quiz"
    assert state["push_subscribed"] is False

    r = await client.post("/api/v1/learn/message", json={"interactive_id": "bad id!"}, headers=auth(token))
    assert r.status_code == 422

    r = await client.get("/api/v1/learn/state")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_token_cannot_use_learner_endpoints(client, test_db):
    from app.utils.auth import create_access_token, get_password_hash
    admin = User(phone_number="+2348000000000", name="Admin", role="admin", hashed_password=get_password_hash("x"), consent_given=True)
    test_db.add(admin)
    await test_db.commit()
    await test_db.refresh(admin)
    token = create_access_token({"sub": str(admin.id)})
    r = await client.get("/api/v1/learn/state", headers=auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_push_subscribe_unsubscribe(client, test_db):
    await seed_days(test_db)
    token = (await enrol(client)).json()["access_token"]
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "P", "auth": "A"}}

    r = await client.post("/api/v1/learn/push/subscribe", json={"subscription": sub, "user_agent": "test"}, headers=auth(token))
    assert r.status_code == 204
    # idempotent on endpoint
    r = await client.post("/api/v1/learn/push/subscribe", json={"subscription": sub}, headers=auth(token))
    assert r.status_code == 204
    rows = (await test_db.execute(select(PushSubscription))).scalars().all()
    assert len(rows) == 1 and rows[0].p256dh == "P"

    r = await client.get("/api/v1/learn/state", headers=auth(token))
    assert r.json()["push_subscribed"] is True

    r = await client.post("/api/v1/learn/push/subscribe", json={"subscription": {"endpoint": "http://insecure", "keys": {}}}, headers=auth(token))
    assert r.status_code == 422

    r = await client.post("/api/v1/learn/push/unsubscribe", json={"endpoint": sub["endpoint"]}, headers=auth(token))
    assert r.status_code == 204
    assert (await test_db.execute(select(PushSubscription))).scalars().all() == []


@pytest.mark.asyncio
async def test_forget_me_deletes_learner(client, test_db):
    await seed_days(test_db)
    token = (await enrol(client)).json()["access_token"]
    r = await client.post("/api/v1/learn/forget-me", headers=auth(token))
    assert r.status_code == 204
    assert (await test_db.execute(select(User))).scalars().all() == []
    r = await client.get("/api/v1/learn/state", headers=auth(token))
    assert r.status_code == 401
