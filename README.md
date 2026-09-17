# MNAIR Platform v2 — Make Nigeria AI Ready (WhatsApp-free)

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![Lessons](https://img.shields.io/badge/lessons-175-orange)]()
[![Languages](https://img.shields.io/badge/languages-5-purple)]()
[![Channels](https://img.shields.io/badge/channels-Telegram%20%7C%20Web%20%7C%20USSD-blue)]()

## Overview

**Make Nigeria AI Ready (MNAIR)** is a national AI literacy initiative that
teaches Nigerians the basics of Artificial Intelligence in 7 days, in 5
languages (English, Pidgin, Hausa, Yoruba, Igbo), with a quiz after every
lesson and a verifiable certificate at the end.

**v2 is the same programme with WhatsApp removed.** From 1 October 2026 Meta
bills every WhatsApp Business conversation — including replies to messages a
learner starts — so a free national course can no longer run on it. v2
delivers the identical 175-lesson curriculum over two channels that cost
nothing per message:

| Channel | How learners use it | Cost per message | Reminders |
|---|---|---|---|
| **Telegram bot** | Tap `t.me/<bot>` → press Start → buttons for language, quiz answers, next day | ₦0 (Bot API is free) | Free, sent by the bot |
| **Web learner app** | Open `mnair.ng/learn` in any phone browser → phone number + PIN → chat-style lessons | ₦0 | Free, via Web Push notifications |
| USSD `*384*8080#` | Unchanged (feature phones, no data) | Telco-billed (unchanged) | SMS only if `SMS_REMINDERS_ENABLED=true` |

Both free channels drive **one channel-agnostic conversation engine**
(`backend/app/engine/`), which is the old WhatsApp state machine lifted out of
the WhatsApp adapter. Adding another free channel later (e.g. Facebook
Messenger if its pricing stays free, or an SMS aggregator with a flat fee) is
a ~200-line adapter, not a rewrite.

### Key Features (unchanged from v1)

- 7-Day AI Literacy Program — 5 lessons/day, 60% to pass, 3 attempts per quiz
- 5 Nigerian languages, 175 lessons with shuffled quiz options
- Verifiable PDF certificates (`/verify`)
- Admin dashboard: analytics, channel/language/engagement reports, reminder stats
- Employer certificate search API
- NDPA-aware: explicit consent, 90-day retention job, learner self-erasure (`/learn` → *Delete my account*)

## What changed from v1 (mnair / advancemnair)

| Area | v1 | v2 |
|---|---|---|
| Learner chat channel | `channels/whatsapp.py` (Meta Cloud API) | `engine/` + `channels/telegram.py` + `channels/web.py` |
| Outbound reminders | WhatsApp 24h-window nudges + SMS | `channels/notify.py` routes **free-first**: Telegram → Web Push → (SMS only if enabled) |
| Learner web sign-in | passwordless by phone number | phone + PIN (bcrypt), no SMS OTP cost |
| Landing page | "Start on WhatsApp" | "Learn in your browser" + "Start on Telegram" |
| New page | — | `/learn` — chat UI, PWA installable, push opt-in, progress bar |
| New tables/columns | — | `push_subscriptions`; `users.telegram_chat_id`, `users.learner_pin_hash`; channel enum `+telegram, +web` |
| Removed | WhatsApp webhook, test simulator, `META_*` settings, WhatsApp tests & shell scripts | — |
| Kept | USSD, SMS (opt-in), KingsChat (feature-flagged), certificates, analytics, admin, employers | — |

## Quick start (local)

```bash
# 1. Backend
cd backend
python -m venv venv && ./venv/Scripts/activate   # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env                        # fill JWT_SECRET_KEY, SESSION_SECRET, DB creds

# Option A — full stack (PostgreSQL/Redis/MinIO via Docker)
docker-compose up -d db redis minio
python init_db_simple.py && python create_admin.py && python load_curriculum.py
# Option B — zero-infra smoke run on SQLite (no certificates/celery)
#   DATABASE_URL=sqlite+aiosqlite:///./mnair.db python init_db_simple.py && ...

python -m uvicorn app.main:app --reload            # http://localhost:8000/docs

# 2. Telegram bot (dev: long-polling, no public URL needed)
#    Create a bot with @BotFather, put the token in .env, then:
python telegram_bot.py

# 3. Frontend
cd ../frontend && npm ci && npm run dev             # http://localhost:3000
#    Learner app:   http://localhost:3000/learn
#    Admin:         http://localhost:3000/login
```

Without `TELEGRAM_BOT_TOKEN` the bot client runs in dev mode and logs every
outbound message instead of sending it, so the whole flow (including the
webhook) can be exercised offline.

## Production deployment (Docker Compose)

```bash
cp .env.example .env    # set every REQUIRED value, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, VAPID keys
docker-compose up -d --build
docker-compose exec backend python init_db_simple.py
docker-compose exec backend python load_curriculum.py
docker-compose exec backend python create_admin.py

# Telegram — webhook mode (API reachable on public HTTPS)
docker-compose exec backend python telegram_bot.py --set-webhook https://api.mnair.ng/api/v1/webhooks/telegram
# ...or polling mode if there is no public URL:
docker-compose --profile telegram-poll up -d telegram_bot
```

**Migrating an existing v1 database** (keeps every learner, lesson, progress row and certificate):

```bash
docker-compose exec backend python migrate_v2_channels.py
```

It adds the two enum values, the two `users` columns and the
`push_subscriptions` table, and unassigns former WhatsApp learners from a
channel (they re-enter through Telegram or `/learn`; their `current_day` and
progress are intact, and a former USSD/WhatsApp learner who signs in on the web
with their phone number claims a PIN on first login).

### Web Push keys (one-off)

```bash
cd backend && python -c "from app.channels.webpush import generate_vapid_keys as g; print(g())"
```

Paste both values into `.env`. Without them the learner app hides nothing —
the bell icon simply reports that reminders aren't configured yet.

## API surface added in v2

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/webhooks/telegram` | Telegram update webhook (secret-token checked) |
| `GET` | `/api/v1/learn/config` | Telegram link, VAPID public key, PIN policy |
| `POST` | `/api/v1/learn/enrol` | phone + PIN + consent → token + welcome messages |
| `POST` | `/api/v1/learn/login` | phone + PIN → token |
| `GET` | `/api/v1/learn/state` | thread history + progress (restores the app after reload) |
| `POST` | `/api/v1/learn/message` | one turn: `{text}` or `{interactive_id}` → replies |
| `POST` | `/api/v1/learn/push/subscribe` · `/unsubscribe` | Web Push subscriptions |
| `POST` | `/api/v1/learn/forget-me` | NDPA erasure |

Removed: `GET/POST /api/v1/webhooks/whatsapp`, `/api/v1/test/whatsapp/*`.

## Background tasks (Celery Beat, Africa/Lagos)

| Task | Schedule | Channel |
|---|---|---|
| `send_daily_nudges` | hourly | learners quiet 20–23h → Telegram / Web Push (never SMS) |
| `send_inactive_user_reminders` | 10:00 daily | 3/7/14-day reminders → free channels first, SMS only if enabled |
| `auto_generate_certificates` | 02:00 daily | generate + notify over free channel |
| analytics, cleanup, backups | unchanged | — |

## Tests

```bash
cd backend
JWT_SECRET_KEY=test SESSION_SECRET=test pytest tests --ignore=tests/test_kingschat_flow.py
```

New in v2: `test_engine_flow.py` (full Day 1→7 flow, retries, language
switch, certificate naming), `test_telegram_channel.py` (rendering, keyboards,
webhook), `test_web_learn.py` (enrol/PIN/turns/push/erasure),
`test_notifications.py` (free-first routing, nudge dedupe, SMS gating).
`test_kingschat_flow.py` needs `playwright` installed.

## Project structure

```
mnair-v2/
├── backend/
│   ├── app/
│   │   ├── engine/            # ★ channel-agnostic conversation engine
│   │   │   ├── conversation.py   state machine (ex-WhatsApp handler, no I/O)
│   │   │   ├── builder.py        every learner-facing message
│   │   │   ├── messages.py       OutboundMessage / Button
│   │   │   └── identity.py       learner lookup ("tg:{chat_id}", +234…)
│   │   ├── channels/
│   │   │   ├── telegram.py    # ★ Bot API client, renderer, webhook
│   │   │   ├── web.py         # ★ /api/v1/learn — browser learner app API
│   │   │   ├── webpush.py     # ★ VAPID push sender
│   │   │   ├── notify.py      # ★ free-first outbound router
│   │   │   ├── ussd.py, sms.py, kingschat.py   (unchanged)
│   │   ├── models/push_subscription.py   # ★
│   │   ├── tasks/notification_tasks.py   # rewritten around notify.py
│   │   └── ...                # routers, services, certificates, analytics (unchanged)
│   ├── telegram_bot.py        # ★ polling runner / webhook registration
│   └── migrate_v2_channels.py # ★ v1 → v2 schema migration
├── frontend/src/pages/Learn.tsx   # ★ chat learner app (+ public/sw.js, manifest)
├── curriculum/                # 175 YAML lessons (unchanged)
└── docker-compose.yml         # + optional telegram_bot polling service
```

## Cost model

| Item | v1 (WhatsApp) | v2 |
|---|---|---|
| Learner ↔ bot messages | per-conversation (Meta) | ₦0 |
| Daily reminders | free only inside 24h window, else template fee | ₦0 (Telegram / Web Push) |
| Certificate-ready notice | template fee or SMS | ₦0 |
| SMS | reminders + certificates | **off by default** (`SMS_REMINDERS_ENABLED`) |
| USSD | telco session billing | unchanged |

## Documentation

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — production deployment
- [QUICK_START.md](QUICK_START.md) — daily operations
- [TODOS.md](TODOS.md) — open items (v2 section at the top)
- Historical (v1) documents: PROJECT_STATUS.md, MODULE_0_COMPLETE.md, NEXT_STEPS.md
