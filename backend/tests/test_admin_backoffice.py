"""
Admin back office: overview numbers, learner management (search, paging,
phone change, PIN reset, guards on admins), certificate download and share
links (also from the sponsor portal), voiding bank transfers, and the audit
trail every change leaves.

MinIO is faked as "down", so certificate PDFs come from the re-render path.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.certificate import Certificate
from app.models.sponsor import Organization, Payment, SponsorCharge, SponsorCode
from app.models.user import Language, User, UserRole
from app.services import certificate_files
from app.utils.auth import create_access_token, get_password_hash


def bearer(sub):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': sub})}"}


class _DownStorage:
    def get_object(self, *a, **k):
        raise ConnectionError("minio down")


@pytest.fixture(autouse=True)
def storage_down(monkeypatch):
    monkeypatch.setattr(certificate_files, "_storage_client", lambda settings: _DownStorage())


async def make_admin(db, phone="+2348030000000", name="Admin One"):
    admin = User(
        phone_number=phone, name=name, role=UserRole.ADMIN, consent_given=True,
        hashed_password=get_password_hash("admin-password-1"),
    )
    db.add(admin)
    await db.commit()
    return admin


async def make_user(db, phone, name="Learner", **kw):
    user = User(
        phone_number=phone, name=name, name_confirmed=True, role=UserRole.LEARNER,
        language=Language.ENGLISH, consent_given=True, **kw,
    )
    db.add(user)
    await db.commit()
    return user


async def make_org(db, name="Grace Chapel", code="GRACE-2026", deposit=0):
    org = Organization(
        name=name, package="community", price_per_certificate_kobo=250_000, deposit_kobo=deposit,
        contact_email="finance@grace.example", portal_email=f"portal@{code.lower()}.example",
        hashed_password=get_password_hash("portal-password-1"),
    )
    db.add(org)
    await db.flush()
    c = SponsorCode(organization_id=org.id, code=code)
    db.add(c)
    await db.commit()
    return org, c


async def make_cert(db, user, cert_id, access="free", org=None):
    cert = Certificate(
        certificate_id=cert_id, user_id=user.id, learner_name=user.name, learner_phone=user.phone_number,
        language="en", average_quiz_score=88.0, days_to_complete=7, pdf_url=f"certificates/{cert_id}.pdf",
        pdf_filename=f"{cert_id}.pdf", verification_hash=(cert_id * 64)[:64], verification_url="https://mnair.ng/verify",
        access_type=access, organization_id=org.id if org else None, sponsor_name=org.name if org else None,
    )
    db.add(cert)
    await db.commit()
    return cert


async def audit_rows(db, action=None):
    q = select(AdminAuditLog).order_by(AdminAuditLog.id)
    if action:
        q = q.where(AdminAuditLog.action == action)
    return (await db.execute(q)).scalars().all()


# ---------------------------------------------------------------------------
# access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_routes_need_an_admin(test_db, client):
    learner = await make_user(test_db, "+2348031110001")
    org, _ = await make_org(test_db)
    for path in ("/api/v1/admin/overview", "/api/v1/admin/learners", "/api/v1/admin/payments", "/api/v1/admin/audit"):
        assert (await client.get(path, headers=bearer(str(learner.id)))).status_code == 403
        assert (await client.get(path, headers=bearer(f"sponsor:{org.id}"))).status_code == 401


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overview_money_does_not_net_across_sponsors(test_db, client):
    admin = await make_admin(test_db)
    owing, _ = await make_org(test_db, "Owing Church", "OWING-1", deposit=1_000_000)
    ahead, _ = await make_org(test_db, "Prepaid Corp", "AHEAD-1")
    u1 = await make_user(test_db, "+2348031110002", last_active_at=datetime.utcnow())
    await make_user(test_db, "+2348031110003", is_active=False)
    test_db.add_all([
        SponsorCharge(organization_id=owing.id, certificate_code="C1", amount_kobo=500_000, user_id=u1.id),
        SponsorCharge(organization_id=ahead.id, certificate_code="C2", amount_kobo=100_000),
        Payment(reference="P-1", purpose="sponsor_manual", status="success", amount_kobo=200_000,
                organization_id=owing.id, email="x@y.z", paid_at=datetime.utcnow()),
        Payment(reference="P-2", purpose="sponsor_manual", status="success", amount_kobo=900_000,
                organization_id=ahead.id, email="x@y.z", paid_at=datetime.utcnow()),
        Payment(reference="P-3", purpose="certificate", status="success", amount_kobo=200_000, email="l@y.z"),
        Payment(reference="P-4", purpose="certificate", status="pending", amount_kobo=200_000, email="l@y.z"),
    ])
    await test_db.commit()

    r = await client.get("/api/v1/admin/overview", headers=bearer(str(admin.id)))
    assert r.status_code == 200, r.text
    body = r.json()
    rev = body["revenue"]
    assert rev["charged_kobo"] == 600_000
    assert rev["sponsor_collected_kobo"] == 1_100_000
    assert rev["learner_certificate_collected_kobo"] == 200_000
    assert rev["outstanding_kobo"] == 300_000          # owing church only — not offset by Prepaid's credit
    assert rev["sponsor_credit_kobo"] == 800_000
    assert rev["deposits_outstanding_kobo"] == 1_000_000
    assert rev["pending_payments"] == 1
    assert body["sponsors"] == {"total": 2, "active": 2, "owing": 1}
    assert body["learners"]["total"] == 2               # admin not counted
    assert body["learners"]["inactive_accounts"] == 1
    assert body["learners"]["active_last_7_days"] == 1
    assert len(body["trend"]) == 6
    assert body["trend"][-1]["charged_kobo"] == 600_000


# ---------------------------------------------------------------------------
# learners
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_learner_search_filters_and_paging(test_db, client):
    admin = await make_admin(test_db)
    org, code = await make_org(test_db)
    ada = await make_user(test_db, "+2348031234567", "Adaeze Okafor", sponsor_code_id=code.id, completed_days=7)
    await make_cert(test_db, ada, "MNAIR-ADA", access="sponsored", org=org)
    for i in range(30):
        await make_user(test_db, f"+23480399900{i:02d}", f"Bulk Learner {i}")
    h = bearer(str(admin.id))

    r = (await client.get("/api/v1/admin/learners", params={"limit": 10}, headers=h)).json()
    assert r["total"] == 32 and len(r["items"]) == 10      # 31 learners + the admin

    # Local phone format finds the +234 number
    r = (await client.get("/api/v1/admin/learners", params={"q": "08031234567"}, headers=h)).json()
    assert [i["name"] for i in r["items"]] == ["Adaeze Okafor"]
    item = r["items"][0]
    assert item["sponsor"]["name"] == "Grace Chapel" and item["certificate_id"] == "MNAIR-ADA"

    r = (await client.get("/api/v1/admin/learners", params={"sponsor_id": org.id}, headers=h)).json()
    assert r["total"] == 1
    r = (await client.get("/api/v1/admin/learners", params={"certified": "true"}, headers=h)).json()
    assert r["total"] == 1
    r = (await client.get("/api/v1/admin/learners", params={"role": "learner", "certified": "false"}, headers=h)).json()
    assert r["total"] == 30

    detail = (await client.get(f"/api/v1/admin/learners/{ada.id}", headers=h)).json()
    assert detail["sponsor"]["code"] == "GRACE-2026"
    assert detail["certificates"][0]["certificate_id"] == "MNAIR-ADA"
    assert detail["has_pin"] is False


@pytest.mark.asyncio
async def test_change_phone_reset_pin_and_audit(test_db, client):
    admin = await make_admin(test_db)
    user = await make_user(test_db, "+2348031110010", learner_pin_hash=get_password_hash("1234"))
    other = await make_user(test_db, "+2348031110011")
    h = bearer(str(admin.id))

    # New SIM: the number moves, progress stays on the same account
    r = await client.patch(f"/api/v1/admin/learners/{user.id}", headers=h, json={"phone_number": "08059998888"})
    assert r.status_code == 200, r.text
    await test_db.refresh(user)
    assert user.phone_number == "+2348059998888"

    r = await client.patch(f"/api/v1/admin/learners/{user.id}", headers=h, json={"phone_number": other.phone_number})
    assert r.status_code == 409

    r = await client.post(f"/api/v1/admin/learners/{user.id}/reset-pin", headers=h)
    assert r.status_code == 200
    await test_db.refresh(user)
    assert user.learner_pin_hash is None

    # Learner signs in with the new number and picks a fresh PIN
    r = await client.post("/api/v1/learn/login", json={"phone_number": "08059998888", "pin": "4321"})
    assert r.status_code == 200, r.text

    actions = [a.action for a in await audit_rows(test_db)]
    assert actions == ["learner.update", "learner.reset_pin"]
    row = (await audit_rows(test_db, "learner.update"))[0]
    assert row.details["phone_number"] == {"from": "+2348031110010", "to": "+2348059998888"}
    assert row.admin_label == "Admin One"


@pytest.mark.asyncio
async def test_admin_guards(test_db, client):
    admin = await make_admin(test_db)
    learner = await make_user(test_db, "+2348031110020")
    h = bearer(str(admin.id))

    r = await client.patch(f"/api/v1/admin/learners/{admin.id}", headers=h, json={"is_active": False})
    assert r.status_code == 409
    r = await client.patch(f"/api/v1/admin/learners/{learner.id}", headers=h, json={"role": "admin"})
    assert r.status_code == 422                          # needs a password to sign in
    r = await client.patch(f"/api/v1/admin/learners/{learner.id}", headers=h,
                           json={"role": "admin", "password": "second-admin-pass"})
    assert r.status_code == 200
    # Now two admins: the second may demote the first, but not the last one
    r = await client.patch(f"/api/v1/admin/learners/{admin.id}", headers=bearer(str(learner.id)), json={"role": "learner"})
    assert r.status_code == 200
    r = await client.patch(f"/api/v1/admin/learners/{learner.id}", headers=bearer(str(learner.id)), json={"is_active": False})
    assert r.status_code == 409
    row = (await audit_rows(test_db, "learner.update"))[0]
    assert row.details["password"] == "(changed)"        # never the password itself


@pytest.mark.asyncio
async def test_remove_sponsor_keeps_billing(test_db, client):
    admin = await make_admin(test_db)
    org, code = await make_org(test_db)
    user = await make_user(test_db, "+2348031110030", sponsor_code_id=code.id, sponsored_at=datetime.utcnow())
    test_db.add(SponsorCharge(organization_id=org.id, certificate_code="C9", amount_kobo=250_000, user_id=user.id))
    await test_db.commit()
    r = await client.post(f"/api/v1/admin/learners/{user.id}/remove-sponsor", headers=bearer(str(admin.id)))
    assert r.status_code == 200
    await test_db.refresh(user)
    assert user.sponsor_code_id is None
    assert len((await test_db.execute(select(SponsorCharge))).scalars().all()) == 1


# ---------------------------------------------------------------------------
# certificates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_downloads_certificate_when_storage_is_down(test_db, client):
    admin = await make_admin(test_db)
    user = await make_user(test_db, "+2348031110040", "Chinedu Eze")
    await make_cert(test_db, user, "MNAIR-CHI")
    h = bearer(str(admin.id))

    r = await client.get("/api/v1/admin/certificates/MNAIR-CHI/pdf", headers=h)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert "MNAIR-certificate-MNAIR-CHI.pdf" in r.headers["content-disposition"]
    assert (await audit_rows(test_db, "certificate.download"))

    listing = (await client.get("/api/v1/admin/certificates", params={"q": "chinedu"}, headers=h)).json()
    assert listing["total"] == 1 and listing["items"][0]["user_id"] == user.id
    assert (await client.get("/api/v1/admin/certificates/NOPE/pdf", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_share_link_opens_without_login_and_only_for_its_certificate(test_db, client):
    admin = await make_admin(test_db)
    user = await make_user(test_db, "+2348031110050", "Bola Ade")
    other = await make_user(test_db, "+2348031110051", "Other Person")
    await make_cert(test_db, user, "MNAIR-BOLA")
    await make_cert(test_db, other, "MNAIR-OTHER")
    await make_cert(test_db, other, "MNAIR-UNPAID", access="pending_payment")
    h = bearer(str(admin.id))

    r = await client.post("/api/v1/admin/certificates/MNAIR-BOLA/link", headers=h, json={"days": 3})
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    token = path.split("?t=")[1]

    r = await client.get(path)                                         # no auth header
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = await client.get(f"/api/v1/certificates/file/MNAIR-OTHER?t={token}")
    assert r.status_code == 404                                        # token is for one certificate
    # The link token is not a login
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await client.get("/api/v1/sponsors/me/dashboard", headers={"Authorization": f"Bearer {token}"})).status_code == 401

    expired = create_access_token(data={"sub": "certfile:MNAIR-BOLA"}, expires_delta=timedelta(seconds=-5))
    assert (await client.get(f"/api/v1/certificates/file/MNAIR-BOLA?t={expired}")).status_code == 404

    r = await client.post("/api/v1/admin/certificates/MNAIR-UNPAID/link", headers=h, json={})
    assert r.status_code == 402
    r = await client.post("/api/v1/admin/certificates/MNAIR-UNPAID/link", headers=h, json={"allow_unpaid": True})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sponsor_gets_only_their_sponsored_certificates(test_db, client):
    org, code = await make_org(test_db)
    rival, _ = await make_org(test_db, "Rival", "RIVAL-1")
    mine = await make_user(test_db, "+2348031110060", "Mine", sponsor_code_id=code.id)
    stranger = await make_user(test_db, "+2348031110061", "Stranger")
    await make_cert(test_db, mine, "MNAIR-MINE", access="sponsored", org=org)
    await make_cert(test_db, stranger, "MNAIR-FREE")
    h = bearer(f"sponsor:{org.id}")

    r = await client.get("/api/v1/sponsors/me/certificates/MNAIR-MINE/pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = await client.post("/api/v1/sponsors/me/certificates/MNAIR-MINE/link", headers=h, json={"days": 7})
    assert r.status_code == 200
    assert (await client.get(r.json()["path"])).status_code == 200

    assert (await client.get("/api/v1/sponsors/me/certificates/MNAIR-FREE/pdf", headers=h)).status_code == 404
    assert (await client.get("/api/v1/sponsors/me/certificates/MNAIR-MINE/pdf",
                             headers=bearer(f"sponsor:{rival.id}"))).status_code == 404


# ---------------------------------------------------------------------------
# sponsors + payments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sponsor_admin_detail_audit_and_void(test_db, client):
    admin = await make_admin(test_db)
    org, code = await make_org(test_db)
    user = await make_user(test_db, "+2348031110070", "Sponsored One", sponsor_code_id=code.id, sponsored_at=datetime.utcnow())
    h = bearer(str(admin.id))

    r = await client.get(f"/api/v1/admin/sponsors/{org.id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["organization"]["has_portal_password"] is True
    assert body["codes"][0]["code"] == "GRACE-2026" and body["codes"][0]["enrolled"] == 1
    assert body["codes"][0]["join_url"].endswith("?code=GRACE-2026")

    learners = (await client.get(f"/api/v1/admin/sponsors/{org.id}/learners", headers=h)).json()
    assert learners["items"][0]["user_id"] == user.id
    portal = (await client.get("/api/v1/sponsors/me/learners", headers=bearer(f"sponsor:{org.id}"))).json()
    assert "user_id" not in portal["items"][0]                       # sponsor never sees ids

    r = await client.patch(f"/api/v1/admin/sponsors/{org.id}", headers=h, json={"is_active": False})
    assert r.status_code == 200
    r = await client.patch(f"/api/v1/admin/sponsors/{org.id}", headers=h, json={"portal_password": "new-portal-pass"})
    assert r.status_code == 200
    r = await client.post(f"/api/v1/admin/sponsors/{org.id}/manual-payment", headers=h,
                          json={"amount_kobo": 500_000, "note": "GTBank ref 123"})
    assert r.status_code == 201
    ref = r.json()["reference"]

    payments = (await client.get(f"/api/v1/admin/sponsors/{org.id}/payments", headers=h)).json()
    assert payments[0]["reference"] == ref

    r = await client.post(f"/api/v1/admin/payments/{ref}/void", headers=h, json={"reason": "duplicate entry"})
    assert r.status_code == 200
    assert (await client.post(f"/api/v1/admin/payments/{ref}/void", headers=h, json={"reason": "again"})).status_code == 409
    sponsor_row = (await client.get("/api/v1/admin/sponsors", headers=h)).json()[0]
    assert sponsor_row["paid_kobo"] == 0                               # voided transfer no longer counts

    ledger = (await client.get("/api/v1/admin/payments", params={"purpose": "sponsor"}, headers=h)).json()
    assert ledger["total"] == 1 and ledger["items"][0]["organization_name"] == "Grace Chapel"
    assert ledger["totals_kobo"] == {"voided": 500_000}

    actions = [a.action for a in await audit_rows(test_db)]
    assert actions == ["sponsor.deactivate", "sponsor.portal_login", "payment.manual", "payment.void"]
    log = (await client.get("/api/v1/admin/audit", params={"action": "payment."}, headers=h)).json()
    assert log["total"] == 2 and "payment.void" in log["actions"]
    pw_row = (await audit_rows(test_db, "sponsor.portal_login"))[0]
    assert pw_row.details == {"portal_password": "(changed)"}


@pytest.mark.asyncio
async def test_paystack_payments_cannot_be_voided(test_db, client):
    admin = await make_admin(test_db)
    org, _ = await make_org(test_db)
    test_db.add(Payment(reference="PSK-1", purpose="sponsor_balance", status="success", amount_kobo=100_000,
                        organization_id=org.id, email="x@y.z"))
    await test_db.commit()
    r = await client.post("/api/v1/admin/payments/PSK-1/void", headers=bearer(str(admin.id)), json={"reason": "test"})
    assert r.status_code == 409
