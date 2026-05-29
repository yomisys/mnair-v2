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

## Completed

*(No completed items yet — add items here as they ship)*
