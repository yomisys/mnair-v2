# MNAIR monetisation: sponsors + verified certificates

The 7-day course stays free for every learner. Money comes from two sources:

1. **Sponsors** (churches, companies, states, NGOs) pay per *certified* learner.
2. **Individual verified certificates** (optional, off by default): an
   unsponsored learner pays ₦2,000 to unlock the verified PDF.

## Price list (kobo in the code, ₦ here)

| Package | Certified learners | ₦ per certificate | Deposit (credited) |
|---|---|---|---|
| community | 50–499 | 2,500 | 125,000 |
| organisation | 500–4,999 | 2,000 | 1,000,000 |
| enterprise | 5,000–49,999 | 1,500 | 7,500,000 |
| national | 50,000+ | set per contract | set per contract |

The defaults live in `PACKAGE_DEFAULTS` (`backend/app/models/sponsor.py`). An
admin can override the price or deposit for any sponsor. A price change only
affects certificates issued after it, because each charge records the price
at the time it was issued.

## How it works

```
admin creates sponsor ──► code GRACE-2026 + join links
                          /learn?code=GRACE-2026   t.me/<bot>?start=GRACE-2026
learner enrols with code ─► users.sponsor_code_id set (cap + expiry enforced)
learner finishes Day 7  ─► certificate issued as "sponsored", sponsor name/logo
                          printed, one sponsor_charges row at the sponsor's price
sponsor portal (/sponsor) ─► dashboard, learner list/CSV (no phone numbers),
                          monthly statement, "Pay deposit"/"Pay balance" (Paystack)
```

Billing is calculated each time it is read, so no stored balance can drift:
`amount due = Σ sponsor_charges − Σ successful sponsor payments`. The deposit
is just the first payment, so the first certificates use it up. Bank
transfers are entered as manual payments in the admin Sponsors page.

The charge rows store no personal data and they outlive the learner. A
learner who erases their account under the NDPA does not change what the
sponsor owes.

## Learner commands (Telegram, web, any channel on the engine)

- `CODE GRACE-2026`, or `/code GRACE-2026` on Telegram, joins a sponsor. A
  learner can only ever have one sponsor.
- A learner waiting at the paywall who enters a valid code gets the
  certificate on the spot. It becomes sponsored and is billed to that sponsor.
- `PAY` (or *Get certificate*) shows the Paystack checkout button again.
  Tapping it repeatedly within 6 hours reuses the same checkout.

## Certificate access types (`certificates.access_type`)

| value | verified (public /verify, PDF download, employer search) |
|---|---|
| free | yes. Paywall off, and every certificate issued before this release |
| sponsored | yes |
| paid | yes |
| pending_payment | no. `/verify` answers 404, download answers 402 |

## Paystack

- Checkout: `POST /transaction/initialize`. One page covers card, bank
  transfer and USSD.
- Confirmation comes from **either** the webhook (`/api/v1/payments/paystack/webhook`,
  HMAC-SHA512 signature check) **or** the callback page (`/payment/callback`).
  The callback page calls `/api/v1/payments/verify/{ref}`, which asks Paystack
  directly. Both paths are idempotent.
- A success whose amount or currency does not match is **not** fulfilled. It
  stays pending with a note for a human to check.

## Go-live checklist

1. `python migrate_v3_sponsors.py` on the existing database. It is
   idempotent, and every existing certificate becomes `free`.
2. Set `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY`. Start with test keys.
3. Paystack dashboard → Settings → API Keys & Webhooks → webhook URL
   `https://<host>/api/v1/payments/paystack/webhook`.
4. Run `python telegram_bot.py` once to refresh the bot's command menu, which adds `/code`.
5. Create the first sponsor in Admin → Sponsors, upload its logo, and send it
   the join link and its portal login.
6. Only when you choose to: `CERTIFICATE_PAYWALL_ENABLED=true`.

### Upgrading to sponsor branding + adverts

Do this once on every existing database (production, staging, local),
**before** starting the new backend:

```bash
# Docker
docker-compose exec backend python migrate_v5_sponsor_branding.py
# or from a venv, inside backend/
python migrate_v5_sponsor_branding.py
```

It adds 11 columns to `organizations`: `brand_color`, `tagline`,
`welcome_message`, `website_url`, the `ad_*` advert fields and
`ad_suspended`. It works on PostgreSQL and SQLite, and you can run it again
safely. A brand-new database doesn't need it. If you skip it, every sponsor
query fails because the new columns are missing.

After it runs:

- Existing sponsors start unbranded with no advert. Their `/s/<CODE>` page
  uses the default green until they fill in the **Brand** tab.
- Logo and advert-image uploads are stored in MinIO, so MinIO must be
  reachable. Text, colour and advert fields work without it.
- Admins can pause a sponsor's advert in Admin → Sponsors → Settings, and
  the sponsor can't turn it back on.

## API

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/sponsors/code/{code}` | public: sponsor name for the join page |
| GET | `/api/v1/sponsors/brand/{code}` | public: branding + live advert for `/s/<CODE>` |
| GET | `/api/v1/sponsors/assets/{org_id}/{logo\|ad_image}` | public: sponsor images |
| POST | `/api/v1/sponsors/login` | sponsor |
| GET/PATCH | `/api/v1/sponsors/me/branding` | sponsor |
| POST/DELETE | `/api/v1/sponsors/me/branding/{logo\|ad_image}` (≤ 1 MB / 2 MB) | sponsor |
| GET | `/api/v1/learn/sponsor` | learner: their sponsor's branding + advert |
| GET | `/api/v1/sponsors/me/dashboard`, `/learners`, `/learners.csv`, `/statement?year&month` | sponsor |
| POST | `/api/v1/sponsors/me/pay` `{purpose: deposit\|balance}` | sponsor (amount computed server-side) |
| GET/POST/PATCH | `/api/v1/admin/sponsors`, `/{id}`, `/{id}/codes`, `/codes/{id}` | admin |
| POST | `/api/v1/admin/sponsors/{id}/logo` (PNG/JPEG ≤ 1 MB) | admin |
| GET | `/api/v1/admin/sponsors/{id}/dashboard`, `/learners`, `/statement` | admin |
| POST | `/api/v1/admin/sponsors/{id}/payment-link`, `/manual-payment` | admin |
| GET | `/api/v1/admin/sponsors/payments/all?status&purpose` | admin |
| POST | `/api/v1/payments/certificate` | learner |
| GET | `/api/v1/payments/verify/{reference}` | public (status only) |
| POST | `/api/v1/payments/paystack/webhook` | Paystack (signed) |
