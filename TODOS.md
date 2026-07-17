# TODOS

## Security (P0 — Must complete before cloud deployment)

### Remove test WhatsApp simulator from production app

**What:** Add environment guard to test_whatsapp_router registration in main.py.

**Why:** `/api/v1/test/whatsapp/simulate` is currently exposed in production without authentication, allowing anyone to create fake users, fake lesson completions, and skip the 7-day curriculum. This contaminates pilot data and is a government partnership disqualifier.

**Context:** `backend/app/main.py` — add `if settings.APP_ENV != "production":` guard before `app.include_router(test_whatsapp_router)`. Also remove the "Testing" tag from Swagger docs in production to avoid NITDA reviewers seeing a test endpoint in the platform documentation.

**Effort:** S
**Priority:** P0
**Depends on:** None

---

### Reimplement security middleware as pure ASGI

**What:** Reimplement `SecurityHeadersMiddleware`, `RequestLoggingMiddleware`, and `InputValidationMiddleware` as pure ASGI middleware (not Starlette BaseHTTPMiddleware).

**Why:** All security middleware is commented out in main.py:70-88 due to Starlette BaseHTTPMiddleware issues. The NDPA compliance claim and security headers claim (X-Content-Type-Options, HSTS, CSP, XSS protection) are inaccurate until this is fixed. NITDA security auditors will check response headers.

**Context:** The middleware classes already exist in `backend/app/middleware/`. The issue is Starlette's BaseHTTPMiddleware conflicts with async generators. Per eng review decision: rewrite using FastAPI's `@app.middleware('http')` decorator (NOT pure ASGI class-based) — this is FastAPI's officially documented approach and handles body reading correctly for InputValidationMiddleware. Register all three in main.py:70-88.

WARNING for InputValidationMiddleware: it reads `await request.body()`. In `@app.middleware('http')`, calling `await request.body()` in the middleware automatically caches the body in `request._body` — downstream handlers can read it again via `await request.body()` without any extra steps. This is FastAPI 0.109 / Starlette 0.36 behavior (confirmed working).

WARNING for CORS ordering: Starlette's `add_middleware` (used for CORS) is LIFO. `@app.middleware('http')` is FIFO. Register the 3 new middlewares BEFORE CORS in main.py to ensure CORS processes OPTIONS preflight requests before InputValidation runs pattern checks on them. Correct order in code: CORS (add_middleware) → then @app.middleware('http') for security, logging, validation in that order (last `@app.middleware('http')` registered runs first).

Bundle: replace all `print()` statements with `logging.getLogger(__name__)` in the same PR.

REQUIRED TESTS (add to `backend/tests/test_middleware.py`):
- `test_input_validation_blocks_sqli` → POST /api/v1/auth/register with `{"phone_number": "' OR 1=1--"}` → 400
- `test_input_validation_passthrough` → POST /whatsapp with valid JSON body → body received correctly by handler (not dropped)
- `test_security_headers_present` → GET /health → response has X-Content-Type-Options, X-Frame-Options
- `test_request_size_limit` → POST with body > 10MB → 413

**Effort:** M (human: ~2-3 days / CC: ~20 min)
**Priority:** P0
**Depends on:** None

---

### Implement and activate employer authentication on 4 endpoints

**What:** Write `get_current_employer` in `backend/app/utils/auth.py`, then wire it into 4 employer endpoints.

**Why:** All 4 employer endpoints are unauthenticated (confirmed by eng review: `get_current_employer` was NEVER implemented — the function does not exist). The `/employers/me` endpoint returns HTTP 501. This exposes PII (phone numbers, user names, certificate IDs) without any auth check — an NDPA violation.

**Context:**
STEP 1 — Write `get_current_employer` in `backend/app/utils/auth.py`. Follow the exact pattern of `get_current_user` (auth.py:96) but parse the `employer:{id}` prefix from the JWT sub field:
```python
async def get_current_employer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Employer:
    credentials_exception = HTTPException(status_code=401, ...)
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, ...)
    sub: str = payload.get("sub")
    if not sub or not sub.startswith("employer:"):
        raise credentials_exception
    employer_id = int(sub.split(":")[1])
    # query Employer by id, return or raise
```

STEP 2 — Update employers.py at lines 162, 183, 247, 286: uncomment `current_employer: Employer = Depends(get_current_employer)`. Also remove the `raise HTTP_501_NOT_IMPLEMENTED` from `/employers/me` and implement the actual profile return.

STEP 3 — Write `backend/tests/test_employer_auth.py` with these required tests:
- `test_employer_search_unauthenticated` → POST /employers/certificates/search without token → 401
- `test_employer_search_authenticated` → with valid employer token → 200 + results
- `test_employer_token_confusion` → user JWT against employer endpoint → 401 (token prefix check)
- `test_employer_cross_tenant_stats` → employer A token against /employers/statistics → returns only A's data
- `test_get_current_employer_invalid_token` → malformed JWT → 401

**Effort:** M (human: ~1 hour / CC: ~10 min)
**Priority:** P0
**Depends on:** None

---

### Credential exposure incident response

**What:** Full incident response for .env committed to git: check for unauthorized usage, rotate all credentials, remove from git history, invalidate JWT tokens.

**Why:** The `.env` file is committed to the git repository. It contains live credentials: JWT_SECRET_KEY, Termii API key, Africa's Talking API key, Meta WhatsApp token. Per the CEO review decision (2026-05-29), this is treated as a full incident, not just a cleanup task.

**Context:**
STEP 1 — INVESTIGATE BEFORE ROTATING (parallel with steps 2-3):
- Africa's Talking: check usage logs at dashboard.africastalking.com for any SMS sent that you didn't send
- Meta WhatsApp Business API: check Meta Developer Console for any API calls you didn't make; notify Meta support that the key may have been exposed (prevents account suspension)
- JWT: identify any admin sessions that may have been active; invalidate all issued tokens by regenerating the JWT secret

STEP 2 — ROTATE:
- Generate new JWT_SECRET_KEY: `python -c "import secrets; print(secrets.token_hex(64))"`
- Revoke and reissue: Termii API key, Africa's Talking API key, Meta WhatsApp token
- Rotate PostgreSQL password, MinIO credentials

STEP 3 — CLEAN HISTORY:
- `pip install git-filter-repo && git filter-repo --invert-paths --path .env`
- Force-push: `git push --force-with-lease origin master`
- Add `.env` to `.gitignore` and verify: `echo ".env" >> .gitignore`

STEP 4 — PREVENT:
- Use cloud provider (Railway/Render) env var injection for production — never commit credentials
- Add pre-commit hook to reject .env commits: `git secrets --install`

**Effort:** M (human: ~1-2 days / CC: ~20 min for git cleanup)
**Priority:** P0
**Depends on:** None — do this FIRST before any other work

---

### Pin bcrypt==3.2.2 in requirements.txt

**What:** Add `bcrypt==3.2.2` to `backend/requirements.txt`.

**Why:** Railway will install latest bcrypt (4.x) which is incompatible with passlib 1.7.4. App crashes at startup with `AttributeError: module 'bcrypt' has no attribute '__about__'`. This is confirmed in passlib's GitHub issues.

**Context:** `backend/requirements.txt` — add one line: `bcrypt==3.2.2`. passlib 1.7.4 works with bcrypt 3.x only.

**Effort:** S (human: 1 min / CC: 1 min)
**Priority:** P0
**Depends on:** None — do before first Railway deploy

---

### Remove hardcoded secret defaults from config.py

**What:** Remove default values for JWT_SECRET_KEY, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, and ADMIN_PASSWORD from config.py. Make them required Pydantic fields.

**Why:** config.py has `JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-this-in-production"` and `MINIO_ACCESS_KEY: str = "minioadmin"` as defaults. If Railway env vars are unset, the app starts with these known public defaults. JWT tokens signed with the known key are forgeable by anyone who reads this file.

**Context:** `backend/app/config.py` — change `JWT_SECRET_KEY: str = "..."` to `JWT_SECRET_KEY: str`. Pydantic will raise `ValidationError` at startup if the env var isn't set: `JWT_SECRET_KEY: field required`. This is the correct behavior. Also add an APP_ENV default of `"development"` explicitly (it's fine for dev; the test router guard requires it). Affected lines: 36, 37, 42, 74.

**Effort:** S (human: ~15 min / CC: ~5 min)
**Priority:** P0
**Depends on:** None

---

### Rotate docker-compose default credentials for production

**What:** Use strong random credentials for PostgreSQL, MinIO, and add Redis authentication for production deployment.

**Why:** docker-compose.yml has `POSTGRES_PASSWORD: mnair_password` and `MINIO_ROOT_USER: minioadmin / minioadmin`. These defaults are probed first by automated scanners. MinIO default credentials give anyone full write access to the certificates bucket.

**Context:** For production (Railway/Render): inject credentials via environment variables, not docker-compose.yml. For local dev, docker-compose.yml defaults are acceptable. Add Redis AUTH configuration: `redis-server --requirepass <REDIS_PASSWORD>`.

**Effort:** S (human: ~30 min)
**Priority:** P0
**Depends on:** Cloud deployment setup

---

## Verification (P1 — Before writing pilot report)

### Verify pilot data integrity

**What:** Run a database query to confirm 254 distinct real phone numbers with LessonProgress records from the pilot dates.

**Why:** The outside voice raised that the analytics simulator in the codebase raises questions about data integrity. Before writing the pilot report, verify via raw database query that the 254 users are real (production phone numbers, not test numbers). This is also needed for NITDA if they request a data export.

**Context:** Query: `SELECT COUNT(DISTINCT phone_number) FROM users WHERE created_at BETWEEN '2026-[pilot-start]' AND '2026-[pilot-end]'`. Cross-reference with `SELECT COUNT(*) FROM lesson_progress WHERE user_id IN (...)`. Confirm no test phone numbers (e.g., +2348000000000 admin account) are in the 254 count. Export the result as a CSV — this is the evidence base for the pilot report.

**Effort:** S (human: ~1 hour / CC: ~10 min)
**Priority:** P1
**Depends on:** None

---

### Verify USSD channel end-to-end

**What:** Test the USSD flow end-to-end on Africa's Talking sandbox after credential rotation.

**Why:** The outside voice flagged that Africa's Talking keys were committed to git. If rotated, the USSD channel needs to be re-verified. USSD is the core channel for feature phone users (the key differentiator). If it's broken after key rotation, the platform's main value proposition doesn't work.

**Context:** Africa's Talking sandbox: `africastalking.com/sandbox`. Dial the USSD code (*384*8080# or the configured code), go through the 7-state menu, verify session timeout (90s), and verify a complete lesson flow. Also confirm the new API key is configured in `.env` and the Celery worker can reach Africa's Talking.

**Effort:** S (human: ~2 hours / CC: n/a — manual test)
**Priority:** P1
**Depends on:** Credential rotation (P0)

---

## Deployment (P1 — Before NITDA demo, by 2026-06-27)

### Implement real health checks in /health endpoint

**What:** Replace hardcoded `{"database": "connected"}` with actual connectivity checks in `backend/app/main.py`'s `/health` endpoint.

**Why:** Railway uses the /health endpoint for deploy verification. Currently it always returns 200 OK even if PostgreSQL, Redis, or MinIO are unreachable. A misconfigured Railway deploy silently passes health checks and is only discovered when demo users get errors.

**Context:** `backend/app/main.py` — rewrite the `health_check()` function to: (1) `await db.execute(text('SELECT 1'))` for DB, (2) `redis.ping()` for Redis, (3) MinIO `list_buckets()` or bucket exists check. Return 200 if all pass, 503 with details if any fail. About 30 lines. Inject db and redis via Depends().

**Effort:** S (human: ~1 hour / CC: ~5 min)
**Priority:** P1
**Depends on:** Cloud deployment credentials (need real service URLs)

---

### Deploy to cloud (Railway + Vercel) with live demo URL

**What:** Deploy backend to Railway, frontend to Vercel, MinIO → AWS S3 or Railway storage, PostgreSQL via Railway managed database.

**Why:** The NITDA application requires a live demo URL. Currently running on localhost only.

**Context:** Backend uses async FastAPI + PostgreSQL + Redis + MinIO. Railway supports Python + managed PostgreSQL. Use Vercel for static React frontend (already Vite-built). Replace MinIO with AWS S3 (boto3/aiobotocore already likely available) for certificate storage. Update .env.example with all required production variables.

**Effort:** M (human: ~3-5 days / CC: ~30 min for config)
**Priority:** P1
**Depends on:** P0 credential rotation

---

### Diagnose and fix 2 failing WhatsApp tests

**What:** Run `backend/tests/test_whatsapp_flow.py`, identify which 2 tests fail, and fix them.

**Why:** 13/15 passing (87%). Unknown failures are unknown edge cases that could surface during the NITDA demo at scale.

**Context:** Likely failures are tests requiring WhatsApp API credentials or database setup that differs from the CI environment. Run with `conftest.py` mock setup to isolate. Fix or mark as integration-only with appropriate pytest markers.

**Effort:** S (human: ~2 hours / CC: ~15 min)
**Priority:** P1
**Depends on:** Cloud deployment environment

---

## Analytics (P2 — Before demo if time allows)

### Fix analytics completions_today tracking

**What:** Implement daily completion count in `backend/app/analytics/service.py:154`.

**Why:** Admin dashboard always shows "0 completions today" even when learners are active. The `completions_today = 0` is hardcoded. NITDA admin demo would show 0 even with real activity.

**Context:** `analytics/service.py:154` — the `completions_today` field is hardcoded to 0 with a TODO comment. The model and other daily query patterns already exist (see `lessons_completed_today` query nearby). Add a query for LessonProgress records where `completed_at` falls within today's date range and `lesson_day == 7` (or use `is_completed == True` and `completed_at >= start_of_day`).

**Effort:** S (human: ~1 hour / CC: ~10 min)
**Priority:** P2
**Depends on:** None

---

## Documentation (P1 — Before NITDA submission)

### Write NDPA Summary for Government Partners

**What:** Create a one-page plain-English NDPA compliance summary for government reviewers.

**Why:** SECURITY.md is written for engineers. NITDA reviewers need a non-technical description of data handling, consent, retention, and privacy controls.

**Context:** Source material in `backend/SECURITY.md`. Write a separate `docs/NDPA_COMPLIANCE_SUMMARY.md` covering: what data is collected, why, how long it's kept, who has access, how users can delete their data, and the legal basis under the Nigeria Data Protection Act. One page maximum.

**Effort:** S (human: ~2 hours / CC: ~15 min)
**Priority:** P1
**Depends on:** None

---

## KingsChat Channel

### Resolve the remaining design-doc Open Questions before real users are exposed

**What:** Three items from `yomis-master-design-20260712-032947.md` are still unresolved and are
founder-level calls, not engineering ones: (1) the ToS check ("The Assignment" — 30 minutes
re-reading KingsChat's actual terms for automation/bot language, never confirmed done), (2) the
leader's concrete distribution commitment (a specific group, member count, date — not just
interest), (3) whether groups/broadcasts are in scope for v1 or DM-only (as currently
implemented) is acceptable to start.

**Why:** The design doc is explicit that the ToS check and the leader's concrete commitment
"should land before real users are exposed to the bot, even though they don't block starting the
build itself" — the build is now functionally complete (see Completed below), which makes this
the actual remaining gate before a `--live` run against real learners.

**Effort:** S (founder time, not engineering)
**Priority:** P0 — blocks going live, not blocks building
**Depends on:** None

---

### Rotate the @yomimnair password

**What:** The account password was shared in a chat transcript during the 2026-07-17 credential
fix. Rotate it once testing settles, and update `backend/.env` to match.

**Effort:** S (founder action)
**Priority:** P1
**Depends on:** None

---

### KingsChat throughput ceiling — the honest math, and what "1000s of users" actually requires

**The physics:** every KingsChat send is real browser automation through ONE account: navigate
(~10-20s with this SPA's hydration), compose, confirm — ~30-60s per message, and a chunked
lesson is 2-3 messages. One serving of one learner interaction (read their message + send the
reply) costs roughly 1-2 minutes of browser time.

**What the current architecture delivers** (post-2026-07-17 hardening: bounded-concurrency
workers via `KINGSCHAT_CONCURRENCY`, capped rotating direct poll via
`KINGSCHAT_DIRECT_POLL_CAP`): with concurrency 3, roughly **90-180 learner interactions/hour**
sustained, with per-learner response latency of one-to-a-few poll cycles. A lesson+quiz round
is ~8 interactions, so think **~15-25 learners actively mid-lesson per hour**, or a few hundred
casually-paced learners per day. Raising concurrency raises throughput linearly AND raises the
odds of the single bot account being flagged — every worker is another simultaneous automated
stream from one identity.

**What it can NEVER deliver, regardless of code:** thousands of *concurrent real-time* learners
through one automated account. The ceilings are structural: one account, one inbox, human-speed
UI automation, and a platform with no bot API whose anti-automation posture is unknown (ToS
check still pending above). The options that actually reach that scale, in rough order of
realism:

1. **WhatsApp/USSD as the scale channels** (already built, API-based, stateless webhooks —
   horizontally scalable to thousands today; DB pool 10+20 and 2 uvicorn workers are the current
   knobs to raise). KingsChat remains the niche channel for the WhatsApp-forbidden audience, at
   its natural pace.
2. **Broadcast/group model for KingsChat** (the design doc's Approach C hybrid): the leader or
   a SuperUser account broadcasts lessons to a group; quizzes happen on a web link (reusing the
   verify-page pattern). One send serves N learners — removes the per-learner send cost
   entirely. Needs the group-automation work that was explicitly scoped out (Open Question 5).
3. **Official API access** via the leader's LoveWorld connections (design doc Approach A) —
   the only path to true per-learner scale on KingsChat itself.
4. **Account sharding** (multiple bot accounts, learners partitioned) — multiplies throughput
   linearly but multiplies ToS exposure and operational surface; per-context proxies
   (`KINGSCHAT_CONTEXT_PROXY_SERVER`) become relevant here. Not recommended before the ToS
   question is answered.

**Also done as part of this hardening** (2026-07-17): the bot no longer dies on a single
learner's failure (per-conversation isolation), survives whole-cycle failures with exponential
backoff, distinguishes session expiry from a ban by attempting re-login before giving up,
drains cleanly on SIGTERM (docker stop), and bounds cycle time via the direct-poll cap.

**Priority:** P1 — decision needed before the leader's distribution commitment lands
**Depends on:** ToS check (above); leader's actual scale number

---

## Completed

### First-contact discovery + correct-account end-to-end run (2026-07-17, third pass)

The full production path now works, verified live on the REAL bot account:

- `backend/.env` updated with @yomimnair's credentials; fresh login passed the identity guard
  (`handle=yomimnair expected=yomimnair match=True`) and the session was saved.
- **Requests-inbox question resolved without needing chip navigation at all**: on @yomimnair's
  own inbox, a real pending first-contact request appeared as a normal unread
  `PrivateConversationBox` row in the DEFAULT view. `list_unread_direct_conversation_ids` no
  longer clicks any tab/chip — the chips are user-configurable ("Edit filters"), `text=Direct`
  matched nothing on one account's configuration, chip clicks were flaky, and a Direct-filtered
  view risks hiding exactly the first-contact threads that matter. Scanning the default view
  with the component-scoped unread selector covers established DMs and requests, and ignores
  groups. Replying to a request implicitly accepts it (verified live twice).
- Live polling discovered the learner thread by display name, clicked it, extracted the
  conversation ID (same ID both parties see), read the latest incoming message, ran the state
  machine, and sent the multi-line welcome **as ONE message from @yomimnair** — first live
  validation of the fragmentation fix (the same welcome went out as ~7 fragments the day
  before).
- Two more hydration races fixed with the same bounded-wait pattern as the rest: the inbox row
  list and the message-bubble list both render seconds after navigation; instant scans saw
  empty lists on non-empty threads (one skipped a real learner mid-poll).
- `read_latest_incoming_message` now collapses whitespace runs — bubble text_content() returns
  one text node per word ('Get          a          certificate'), which would have corrupted
  multi-word input like certificate names.
- `--only-contact` documentation corrected: rows show the contact's DISPLAY NAME
  ("Dcn Yomi(CGDR) CE LZ1"), never the @handle.

### Session identity verification + message fragmentation + stranded-learner recovery (2026-07-17, second pass)

Follow-up to the first live test, driven by deeper live probes of the same thread:

1. **Wrong-account discovery.** Every bubble in the test thread was right-aligned/`--actor` —
   because every message really WAS sent by the logged-in account: the stored session (captured
   2026-07-12 during selector verification "against the founder's own account") belonged to
   `@dcnyomi`, not `@yomimnair`. The whole first live test ran as the founder. The
   `--actor`-misclassification item is thereby RESOLVED AS NOT A BUG: `--actor` = sent by the
   logged-in account, correct all along; `read_latest_incoming_message()` returning None was the
   correct answer for a thread with no incoming messages. Fix shipped: `KINGSCHAT_EXPECTED_USERNAME`
   setting + `get_logged_in_username()` (reads the sidebar `/user/{handle}` profile link, verified
   live) + identity verification in `ensure_logged_in` on BOTH the stored-session and fresh-login
   paths — wrong stored session is discarded, wrong fresh login hard-fails without saving. The
   guard caught both layers live on its first run.
2. **Message fragmentation.** `.type()` presses real Enter for every `\n`, and Enter SUBMITS in
   this Tiptap composer — the first live lesson went out as ~30 separate rapid-fire messages
   (plus partial duplicate sets from the two timed-out attempts before it). Exactly the risk the
   2026-07-12 notes flagged as untested. `send_message` now inserts line content via
   `insert_text()` (no per-keystroke typing — also kills the measured 79s-per-lesson type time
   and the need for a length-scaled timeout) with `Shift+Enter` soft breaks, and never presses
   bare Enter. Regression test asserts Enter is never pressed.
3. **Stranded-learner recovery** (was the P1 "harden lesson delivery" item): `handle_lesson_flow`
   in BOTH kingschat.py and whatsapp.py now re-delivers the lesson on ANY reply when no lesson is
   on record, instead of sending a "Reply QUIZ" reminder about a lesson that never arrived.
   Recovery no longer depends on the learner guessing the magic word.

### First real live test — full curriculum delivery over KingsChat, end to end

**Completed 2026-07-17.** Login (`@yomimnair`, the bot account) → real learner (`@dcnyomi`) sends
START → welcome message + language menu sent for real → learner replies 1 → language recorded →
Day 1 lesson ("What is AI?") delivered in full and confirmed readable by the learner. First time
any of this code sent a real message to a real KingsChat account. Found and fixed four real bugs
along the way that no mocked test could have caught:

1. `users.phone_number` / `conversations.phone_number` / `certificates.learner_phone` were all
   `VARCHAR(15)` (sized for phone numbers) — a real KingsChat conversation ID plus the `kc:`
   prefix runs ~52 chars. Every KingsChat learner's first message would have failed outright with
   `StringDataRightTruncationError`. Widened to `VARCHAR(64)` in `app/models/{user,conversation,
   certificate}.py`; migration in `backend/widen_kingschat_identity_columns.py` for already-deployed
   databases. Added a schema-contract test (`test_identity_columns_wide_enough_for_a_real_
   conversation_id`) since the in-memory SQLite test DB doesn't enforce `VARCHAR(n)` at all —
   this bug was invisible to all 41 prior tests.
2. `_goto_and_settle`'s `page.goto()` could time out even when navigation genuinely succeeded
   (confirmed by inspecting the real page content immediately after the exception) — now
   swallowed the same way the existing `networkidle` wait already was, with a longer bound.
3. The composer-presence check used an instant `.count()` snapshot instead of a bounded wait,
   unlike the adjacent Send-button check — caused a false `SelectorDriftError` on a conversation
   proven seconds earlier to have a working composer. Now uses `wait_for(state="visible")`,
   matching the Send button's already-correct pattern.
4. `.type()`'s default 30s timeout wasn't enough for real lesson content (~1900 chars typed
   keystroke-by-keystroke into a Tiptap/ProseMirror editor) — a short reply worked fine, the
   actual Day 1 lesson timed out. Timeout now scales with content length.

Also surfaced three follow-ups now tracked above (Requests-tab support, the outgoing/incoming
misclassification on first-contact threads, and the commit-before-send-confirmed reliability
gap) — none of which blocked completing this test, since the conversation ID was supplied
manually rather than discovered via normal polling.

### Verify Playwright BrowserContext fingerprint isolation before pooling

**Resolved 2026-07-17.** The premise didn't apply to the architecture actually built: every
context `KingsChatBrowserPool` creates carries the *same* `storage_state` (see
`_context_options()` in `kingschat_browser_pool.py`) — there is one automated KingsChat account
(Open Question 1 resolved to a single shared bot account), not one account per learner. Pooling
exists purely to parallelize page operations under that one already-known identity, so
cross-context fingerprint correlation is moot: pool size adds no distinguishing signal beyond
what a single context under this account already exposes. Confirmed via research that Playwright
`BrowserContext`s do NOT isolate IP, TLS fingerprint, or most GPU/canvas signals regardless —
that fact just doesn't matter for a single-identity pool.

The risk that *does* apply regardless of pool size — standard single-account headless-detection
signals (`navigator.webdriver`, HeadlessChrome markers) — got mitigated as part of closing this
out: `--disable-blink-features=AutomationControlled` on browser launch plus a `navigator.webdriver`
override via `context.add_init_script()` on every acquired context. See
`backend/app/services/kingschat_browser_pool.py`.

### Fix certificate "being generated" dead end in kingschat.py

`handle_day_complete`'s `CERTIFICATE` branch said "being generated" and never called the
generator — same bug independently fixed in `whatsapp.py` the same day. `CERTIFICATE` is now a
global command reachable from any conversation state (mirrors the WhatsApp fix, including
reaching a learner whose conversation reset to `NEW_USER`), generates the certificate
synchronously, and sends the download link immediately.

### Wire the KingsChat channel into deployment

Added `backend/Dockerfile.kingschat` (separate image so the main backend doesn't carry a full
headless Chromium install), a profile-gated `kingschat_bot` service in `docker-compose.yml`
(`docker compose --profile kingschat up -d kingschat_bot` — never starts on a plain `up`), all
`KINGSCHAT_*` vars documented in `.env.example`, and `backend/.dockerignore` (previously missing
entirely — `COPY . .` was baking `backend/.env` and the encrypted KingsChat session into every
image layer). Also fixed the `.gitignore` rule for the session file, which never matched the
filename the code actually produces.
