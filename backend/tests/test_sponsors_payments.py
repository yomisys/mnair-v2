"""
Sponsorship + payments: code redemption rules, certificate billing and
branding, the learner paywall, Paystack webhook/verify, sponsor billing,
and the admin/sponsor-portal API.

MinIO and Paystack are faked; the real CertificateGenerator logic
(access decision, sponsor charge, PDF rendering) runs.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.channels import telegram as tg
from app.config import Settings, get_settings
from app.engine import ConversationEngine, get_or_create_conversation
from app.models.certificate import Certificate
from app.models.conversation import ConversationChannel, ConversationState
from app.models.sponsor import Organization, Payment, SponsorCharge, SponsorCode
from app.models.user import Language, User, UserRole
from app.services import sponsorship
from app.services.payments import confirm_payment, record_manual_payment
from app.services.paystack import PaystackClient
from app.utils.auth import create_access_token, get_password_hash
from tests.test_engine_flow import seed_days
from tests.test_telegram_channel import CapturingClient

SECRET = "sk_test_secret"


def make_settings(**extra):
    return Settings(JWT_SECRET_KEY="t", SESSION_SECRET="t", **extra)


PAYWALL = dict(CERTIFICATE_PAYWALL_ENABLED=True, PAYSTACK_SECRET_KEY=SECRET)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def offline_generator(monkeypatch):
    """Real generator logic, no MinIO."""
    from app.certificates.generator import CertificateGenerator

    def init(self, db, settings):
        self.db, self.settings, self.minio_client = db, settings, None

    async def upload(self, pdf_bytes, code):
        assert pdf_bytes.startswith(b"%PDF")
        return f"certificates/{code}.pdf"

    monkeypatch.setattr(CertificateGenerator, "__init__", init)
    monkeypatch.setattr(CertificateGenerator, "upload_to_minio", upload)
    monkeypatch.setattr(CertificateGenerator, "fetch_logo", lambda self, name: None)


@pytest.fixture
def paystack(monkeypatch):
    state = {"init": [], "verify": {}}

    async def initialize(self, *, email, amount_kobo, reference, metadata=None):
        state["init"].append({"email": email, "amount": amount_kobo, "reference": reference, "metadata": metadata})
        return {"authorization_url": f"https://checkout.paystack.com/{reference}", "access_code": "ac_1"}

    async def verify(self, reference):
        return state["verify"].get(reference, {"status": "abandoned"})

    monkeypatch.setattr(PaystackClient, "initialize", initialize)
    monkeypatch.setattr(PaystackClient, "verify", verify)
    return state


async def make_org(db, name="Grace Chapel", price=250_000, deposit=12_500_000, cap=None, code="GRACE-7K2Q", **kw):
    org = Organization(
        name=name, package="community", price_per_certificate_kobo=price, deposit_kobo=deposit,
        learner_cap=cap, contact_email="finance@grace.example", **kw,
    )
    db.add(org)
    await db.flush()
    c = SponsorCode(organization_id=org.id, code=code)
    db.add(c)
    await db.commit()
    return org, c


async def make_graduate(db, phone="+2348031110001", name="Adaeze Okafor"):
    """A learner who finished all 7 days and confirmed their name."""
    user = User(
        phone_number=phone, name=name, name_confirmed=True, role=UserRole.LEARNER,
        language=Language.ENGLISH, current_day=7, completed_days=7, consent_given=True,
    )
    db.add(user)
    await db.commit()
    conv = await get_or_create_conversation(db, user, ConversationChannel.WEB)
    conv.current_state = ConversationState.DAY_COMPLETE
    await db.commit()
    return user, conv


async def make_learner(db, phone):
    user = User(phone_number=phone, name="Web Learner", role=UserRole.LEARNER, language=Language.ENGLISH, consent_given=True)
    db.add(user)
    await db.commit()
    return user


async def cert_of(db, user):
    return (await db.execute(select(Certificate).where(Certificate.user_id == user.id))).scalar_one_or_none()


def signed(body: dict):
    raw = json.dumps(body).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return raw, {"x-paystack-signature": sig, "content-type": "application/json"}


def bearer(sub):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': sub})}"}


# ---------------------------------------------------------------------------
# code redemption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redeem_code_rules(test_db):
    org, code = await make_org(test_db, cap=1)
    a = await make_learner(test_db, "+2348031110010")
    b = await make_learner(test_db, "+2348031110011")

    with pytest.raises(sponsorship.SponsorCodeError, match="doesn't look like"):
        await sponsorship.redeem_code(test_db, a, "!!")
    with pytest.raises(sponsorship.SponsorCodeError, match="couldn't find"):
        await sponsorship.redeem_code(test_db, a, "NOPE-1234")

    # Case/space-insensitive
    result = await sponsorship.redeem_code(test_db, a, " grace-7k2q ")
    assert result.organization.id == org.id and not result.already_applied
    assert a.sponsor_code_id == code.id and a.sponsored_at

    again = await sponsorship.redeem_code(test_db, a, "GRACE-7K2Q")
    assert again.already_applied

    with pytest.raises(sponsorship.SponsorCodeError, match="places are all taken"):
        await sponsorship.redeem_code(test_db, b, "GRACE-7K2Q")

    other, _ = await make_org(test_db, name="Other Org", code="OTHER-AAAA")
    with pytest.raises(sponsorship.SponsorCodeError, match="already linked"):
        await sponsorship.redeem_code(test_db, a, "OTHER-AAAA")


@pytest.mark.asyncio
async def test_inactive_expired_and_code_limit(test_db):
    org, code = await make_org(test_db)
    u = await make_learner(test_db, "+2348031110020")

    code.is_active = False
    await test_db.commit()
    with pytest.raises(sponsorship.SponsorCodeError, match="no longer active"):
        await sponsorship.redeem_code(test_db, u, code.code)

    code.is_active, code.expires_at = True, datetime.utcnow() - timedelta(days=1)
    await test_db.commit()
    with pytest.raises(sponsorship.SponsorCodeError, match="expired"):
        await sponsorship.redeem_code(test_db, u, code.code)

    code.expires_at, code.max_enrolments = None, 0
    await test_db.commit()
    with pytest.raises(sponsorship.SponsorCodeError, match="reached its limit"):
        await sponsorship.redeem_code(test_db, u, code.code)


# ---------------------------------------------------------------------------
# certificates: who pays
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsponsored_certificate_is_free_when_paywall_off(test_db):
    user, conv = await make_graduate(test_db)
    replies = await ConversationEngine(test_db, make_settings()).handle(user, conv, "CERTIFICATE")
    assert replies[-1].kind == "certificate"
    cert = await cert_of(test_db, user)
    assert cert.access_type == "free" and cert.is_verified
    assert (await test_db.execute(select(func.count(SponsorCharge.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_sponsored_certificate_is_billed_once_and_branded(test_db):
    org, code = await make_org(test_db)
    user, conv = await make_graduate(test_db)
    await sponsorship.redeem_code(test_db, user, code.code)

    engine = ConversationEngine(test_db, make_settings(**PAYWALL))
    replies = await engine.handle(user, conv, "CERTIFICATE")
    assert replies[-1].kind == "certificate"  # paywall never applies to sponsored learners

    cert = await cert_of(test_db, user)
    assert cert.access_type == "sponsored"
    assert cert.organization_id == org.id and cert.sponsor_name == "Grace Chapel"

    await engine.handle(user, conv, "CERTIFICATE")  # idempotent
    charges = (await test_db.execute(select(SponsorCharge))).scalars().all()
    assert len(charges) == 1
    assert charges[0].amount_kobo == 250_000 and charges[0].certificate_code == cert.certificate_id


@pytest.mark.asyncio
async def test_certificate_pdf_renders_sponsor_credit():
    from app.certificates.generator import CertificateGenerator
    gen = CertificateGenerator(None, make_settings())
    plain = gen.create_certificate_pdf("Ada Obi", datetime(2026, 10, 1), "MNAIR-2026-1-AAAAAA")
    branded = gen.create_certificate_pdf(
        "Ada Obi", datetime(2026, 10, 1), "MNAIR-2026-1-AAAAAA", sponsor_name="Grace Chapel", sponsor_logo=b"not an image"
    )
    assert plain.startswith(b"%PDF") and branded.startswith(b"%PDF")
    assert len(branded) > len(plain)  # bad logo falls back to the name, never fails


@pytest.mark.asyncio
async def test_paywall_flow_webhook_unlocks(test_db, client, paystack):
    from app.main import app
    settings = make_settings(**PAYWALL)
    app.dependency_overrides[get_settings] = lambda: settings

    user, conv = await make_graduate(test_db)
    replies = await ConversationEngine(test_db, settings).handle(user, conv, "CERTIFICATE")
    pay = replies[-1]
    assert pay.kind == "payment"
    assert "₦2,000" in pay.text
    link = next(b for b in pay.buttons if b.id == "pay_link")
    assert link.description.startswith("https://checkout.paystack.com/MNAIR-CRT-")
    assert paystack["init"][0]["email"] == f"learner-{user.id}@learners.mnair.ng"  # no phone sent to Paystack

    cert = await cert_of(test_db, user)
    assert cert.access_type == "pending_payment"

    # Not a credential yet: public verify 404, download 402
    r = await client.get(f"/api/v1/certificates/verify/{cert.certificate_id}", params={"name": user.name})
    assert r.status_code == 404
    r = await client.get("/api/v1/certificates/me/download", headers=bearer(str(user.id)))
    assert r.status_code == 402

    # Tapping pay twice reuses the same checkout
    again = await ConversationEngine(test_db, settings).handle(user, conv, "CERTIFICATE")
    assert next(b for b in again[-1].buttons if b.id == "pay_link").description == link.description
    assert len(paystack["init"]) == 1

    reference = pay.meta["reference"]
    # Bad signature rejected
    raw, headers = signed({"event": "charge.success", "data": {"reference": reference}})
    r = await client.post("/api/v1/payments/paystack/webhook", content=raw, headers={**headers, "x-paystack-signature": "bad"})
    assert r.status_code == 401

    # Wrong amount is never fulfilled
    raw, headers = signed({"event": "charge.success", "data": {"reference": reference, "status": "success", "amount": 100, "currency": "NGN"}})
    assert (await client.post("/api/v1/payments/paystack/webhook", content=raw, headers=headers)).status_code == 200
    await test_db.refresh(cert)
    assert cert.access_type == "pending_payment"

    raw, headers = signed({"event": "charge.success", "data": {
        "reference": reference, "status": "success", "amount": 200_000, "currency": "NGN",
        "channel": "bank_transfer", "paid_at": "2026-10-10T09:00:00.000Z",
    }})
    assert (await client.post("/api/v1/payments/paystack/webhook", content=raw, headers=headers)).status_code == 200
    await test_db.refresh(cert)
    assert cert.access_type == "paid"
    payment = (await test_db.execute(select(Payment).where(Payment.reference == reference))).scalar_one()
    assert payment.status == "success" and payment.channel == "bank_transfer"

    # Replay is harmless; callback page sees success
    assert (await client.post("/api/v1/payments/paystack/webhook", content=raw, headers=headers)).status_code == 200
    r = await client.get(f"/api/v1/payments/verify/{reference}")
    assert r.json()["status"] == "success"

    replies = await ConversationEngine(test_db, settings).handle(user, conv, "CERTIFICATE")
    assert replies[-1].kind == "certificate"
    r = await client.get(f"/api/v1/certificates/verify/{cert.certificate_id}", params={"name": user.name})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_callback_verify_unlocks_without_webhook(test_db, paystack):
    settings = make_settings(**PAYWALL)
    user, conv = await make_graduate(test_db)
    pay = (await ConversationEngine(test_db, settings).handle(user, conv, "CERTIFICATE"))[-1]
    ref = pay.meta["reference"]

    assert (await confirm_payment(test_db, settings, ref)).status == "abandoned"
    paystack["verify"][ref] = {"status": "success", "amount": 200_000, "currency": "NGN", "channel": "ussd"}
    assert (await confirm_payment(test_db, settings, ref)).status == "success"
    assert (await cert_of(test_db, user)).access_type == "paid"
    assert await confirm_payment(test_db, settings, "MNAIR-CRT-UNKNOWN") is None


@pytest.mark.asyncio
async def test_payments_down_keeps_learner_informed(test_db):
    settings = make_settings(CERTIFICATE_PAYWALL_ENABLED=True)  # no Paystack key
    user, conv = await make_graduate(test_db)
    reply = (await ConversationEngine(test_db, settings).handle(user, conv, "CERTIFICATE"))[-1]
    assert "payments are unavailable" in reply.text
    assert (await cert_of(test_db, user)).access_type == "pending_payment"


@pytest.mark.asyncio
async def test_code_at_paywall_converts_to_sponsored(test_db, paystack):
    settings = make_settings(**PAYWALL)
    org, code = await make_org(test_db)
    user, conv = await make_graduate(test_db)
    engine = ConversationEngine(test_db, settings)
    await engine.handle(user, conv, "CERTIFICATE")
    assert (await cert_of(test_db, user)).access_type == "pending_payment"

    replies = await engine.handle(user, conv, f"code {code.code}")
    assert "sponsored by *Grace Chapel*" in replies[0].text
    assert replies[-1].kind == "certificate"
    cert = await cert_of(test_db, user)
    assert cert.access_type == "sponsored"
    assert (await test_db.execute(select(func.count(SponsorCharge.id)))).scalar_one() == 1

    # A verified certificate can't be re-billed to another sponsor
    other_user, other_conv = await make_graduate(test_db, phone="+2348031110002")
    await ConversationEngine(test_db, make_settings()).handle(other_user, other_conv, "CERTIFICATE")
    msg = (await engine.handle(other_user, other_conv, f"CODE {code.code}"))[0]
    assert "already have your certificate" in msg.text


@pytest.mark.asyncio
async def test_telegram_deep_link_redeems_and_onboards(test_db):
    await seed_days(test_db)
    org, code = await make_org(test_db)
    settings = make_settings()
    client = CapturingClient(settings)
    channel = tg.TelegramChannel(test_db, settings, client=client)
    await channel.process_update({"update_id": 1, "message": {"chat": {"id": 777, "type": "private"}, "text": f"/start {code.code}"}})

    texts = [m.text for _, m in client.sent]
    assert "Grace Chapel" in texts[0]
    assert [m.kind for _, m in client.sent][-1] == "choice"  # language picker follows
    user = (await test_db.execute(select(User).where(User.telegram_chat_id == "777"))).scalar_one()
    assert user.sponsor_code_id == code.id


# ---------------------------------------------------------------------------
# billing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deposit_is_used_up_first_then_balance_is_due(test_db):
    org, code = await make_org(test_db, price=250_000, deposit=500_000)
    await record_manual_payment(test_db, org, 500_000, "Deposit transfer ref 123")
    for i in range(3):
        test_db.add(SponsorCharge(organization_id=org.id, certificate_code=f"C-{i}", amount_kobo=250_000))
    await test_db.commit()

    acct = await sponsorship.account_summary(test_db, org)
    assert acct["charged_kobo"] == 750_000
    assert acct["paid_kobo"] == 500_000
    assert acct["amount_due_kobo"] == 250_000
    assert acct["credit_remaining_kobo"] == 0

    now = datetime.utcnow()
    st = await sponsorship.monthly_statement(test_db, org, now.year, now.month)
    assert st["certificates_issued"] == 3
    assert st["opening_balance_kobo"] == 0
    assert st["closing_balance_kobo"] == 250_000
    assert len(st["payments"]) == 1


@pytest.mark.asyncio
async def test_learner_erasure_keeps_sponsor_invoice(test_db):
    org, code = await make_org(test_db)
    user, conv = await make_graduate(test_db)
    await sponsorship.redeem_code(test_db, user, code.code)
    await ConversationEngine(test_db, make_settings()).handle(user, conv, "CERTIFICATE")
    await test_db.delete(user)
    await test_db.commit()
    acct = await sponsorship.account_summary(test_db, org)
    assert acct["certificates_billed"] == 1 and acct["charged_kobo"] == 250_000


# ---------------------------------------------------------------------------
# API: admin + sponsor portal + web enrolment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_creates_sponsor_and_sponsor_uses_portal(test_db, client, paystack):
    from app.main import app
    settings = make_settings(PAYSTACK_SECRET_KEY=SECRET, TELEGRAM_BOT_USERNAME="MnairBot")
    app.dependency_overrides[get_settings] = lambda: settings

    admin = User(phone_number="+2348030000000", name="Admin", role=UserRole.ADMIN, email="a@mnair.ng", consent_given=True)
    test_db.add(admin)
    await test_db.commit()

    # Learner can't reach admin routes
    learner = await make_learner(test_db, "+2348031110099")
    assert (await client.get("/api/v1/admin/sponsors", headers=bearer(str(learner.id)))).status_code == 403

    r = await client.post("/api/v1/admin/sponsors", headers=bearer(str(admin.id)), json={
        "name": "Grace Chapel", "package": "community", "contact_email": "finance@grace.example",
        "portal_email": "Pastor@Grace.example", "portal_password": "a-long-password", "first_code": "grace-2026",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"]["code"] == "GRACE-2026"
    assert body["code"]["join_url"].endswith("/learn?code=GRACE-2026")
    assert body["code"]["telegram_url"] == "https://t.me/MnairBot?start=GRACE-2026"
    org_id = body["id"]

    # National package needs explicit prices
    r = await client.post("/api/v1/admin/sponsors", headers=bearer(str(admin.id)), json={
        "name": "Federal", "package": "national", "contact_email": "x@fed.example"})
    assert r.status_code == 422

    org = (await test_db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    assert org.price_per_certificate_kobo == 250_000 and org.deposit_kobo == 12_500_000

    # Public code lookup, then web enrolment with the code
    r = await client.get("/api/v1/sponsors/code/grace-2026")
    assert r.json() == {"code": "GRACE-2026", "sponsor_name": "Grace Chapel"}
    await seed_days(test_db)
    r = await client.post("/api/v1/learn/enrol", json={
        "phone_number": "08031234567", "pin": "2468", "consent_given": True, "sponsor_code": "GRACE-2026"})
    assert r.status_code == 201, r.text
    assert "Grace Chapel" in r.json()["messages"][0]["text"]

    r = await client.post("/api/v1/learn/enrol", json={
        "phone_number": "08031234568", "pin": "2468", "consent_given": True, "sponsor_code": "WRONG-CODE"})
    assert r.status_code == 422
    assert (await test_db.execute(select(User).where(User.phone_number == "+2348031234568"))).scalar_one_or_none() is None

    # Sponsor portal
    r = await client.post("/api/v1/sponsors/login", json={"email": "pastor@grace.example", "password": "wrong"})
    assert r.status_code == 401
    r = await client.post("/api/v1/sponsors/login", json={"email": "pastor@grace.example", "password": "a-long-password"})
    assert r.status_code == 200
    sponsor_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # A sponsor token is not a learner/admin token
    assert (await client.get("/api/v1/learn/state", headers=sponsor_headers)).status_code == 401

    dash = (await client.get("/api/v1/sponsors/me/dashboard", headers=sponsor_headers)).json()
    assert dash["learners"]["enrolled"] == 1
    assert dash["codes"][0]["join_url"].endswith("GRACE-2026")
    assert dash["account"]["deposit_outstanding_kobo"] == 12_500_000

    learners = (await client.get("/api/v1/sponsors/me/learners", headers=sponsor_headers)).json()
    assert learners["total"] == 1
    assert "8031234567" not in json.dumps(learners)  # no phone numbers for sponsors
    csv_r = await client.get("/api/v1/sponsors/me/learners.csv", headers=sponsor_headers)
    assert csv_r.status_code == 200 and csv_r.text.startswith("name,language")

    # Pay deposit: amount is computed server-side
    r = await client.post("/api/v1/sponsors/me/pay", headers=sponsor_headers, json={"purpose": "deposit"})
    assert r.status_code == 200, r.text
    assert r.json()["amount_kobo"] == 12_500_000
    assert paystack["init"][-1]["email"] == "finance@grace.example"
    r = await client.post("/api/v1/sponsors/me/pay", headers=sponsor_headers, json={"purpose": "balance"})
    assert r.status_code == 409  # nothing billed yet

    # Admin records a bank transfer; statement reflects it
    r = await client.post(f"/api/v1/admin/sponsors/{org_id}/manual-payment", headers=bearer(str(admin.id)),
                          json={"amount_kobo": 12_500_000, "note": "GTB transfer 10 Oct"})
    assert r.status_code == 201
    assert r.json()["account"]["credit_remaining_kobo"] == 12_500_000
    st = (await client.get("/api/v1/sponsors/me/statement", headers=sponsor_headers)).json()
    assert st["closing_balance_kobo"] == -12_500_000

    # Deactivating the code stops new learners
    code_id = (await client.get(f"/api/v1/admin/sponsors/{org_id}/codes", headers=bearer(str(admin.id)))).json()[0]["id"]
    r = await client.patch(f"/api/v1/admin/sponsors/codes/{code_id}", headers=bearer(str(admin.id)), json={"is_active": False})
    assert r.json()["is_active"] is False
    assert (await client.get("/api/v1/sponsors/code/GRACE-2026")).status_code == 404


@pytest.mark.asyncio
async def test_logo_upload_rejects_non_images(test_db, client):
    admin = User(phone_number="+2348030000001", name="Admin", role=UserRole.ADMIN, email="b@mnair.ng", consent_given=True)
    test_db.add(admin)
    await test_db.commit()
    org, _ = await make_org(test_db)
    r = await client.post(
        f"/api/v1/admin/sponsors/{org.id}/logo",
        headers=bearer(str(admin.id)),
        files={"file": ("logo.png", b"GIF89a not allowed", "image/png")},
    )
    assert r.status_code == 415
