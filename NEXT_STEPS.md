# Next Steps for Building MNAIR Platform

## ✅ Completed: Foundation Setup

You've successfully completed the initial repository setup:
- ✅ Git repository initialized
- ✅ Complete folder structure created
- ✅ Docker Compose configuration with PostgreSQL, Redis, MinIO
- ✅ Environment variables template (.env.example)
- ✅ Comprehensive .gitignore
- ✅ Detailed README with architecture overview

## 🚦 Before You Start Building Modules

### 1. Start Docker Desktop
The infrastructure services require Docker Desktop to be running:
```bash
# On Windows: Open Docker Desktop application
# Then verify it's running:
docker compose ps
```

### 2. Start Infrastructure Services
Once Docker Desktop is running:
```bash
cd mnair
docker compose up -d db redis minio

# Verify all services are healthy:
docker compose ps

# You should see:
# - mnair_postgres (port 5432)
# - mnair_redis (port 6379)
# - mnair_minio (ports 9000, 9001)
```

### 3. Configure MinIO
Create the certificates bucket:
1. Open http://localhost:9001
2. Login: `minioadmin` / `minioadmin`
3. Create bucket: `mnair-certificates`
4. Set access policy to Public (for certificate verification)

### 4. Fill in API Keys (Optional for Initial Development)
Edit `.env` and add your real API keys:
- `TERMII_API_KEY` - Get from https://termii.com
- `AFRICASTALKING_API_KEY` - Get from https://africastalking.com
- `META_WHATSAPP_TOKEN` - Get from Meta Business Suite

**Note**: You can build Modules 0-3 without API keys. You'll need them for Module 2 (Channels).

---

## 🏗️ Module Build Sequence

Follow this exact order. **One module per Claude conversation.**

### 📦 Phase A: Foundation (Build First)

#### **Session 1: Module 0 — Database Models & Migrations**
**Estimated Time**: 2-3 hours

**Prompt to use**:
```
I am building the Make Nigeria AI-Ready (MNAIR) platform.
I need you to build Module 0: Database Models & Infrastructure.

CONTEXT:
- PostgreSQL, Redis, MinIO are already running via docker-compose
- Folder structure exists: backend/app/models/, backend/migrations/
- Environment variables are configured in .env

YOUR TASK:
Build the complete database schema with SQLAlchemy models:
1. User model (learners, admins, employers)
2. Lesson model (35 lessons, 5 languages)
3. LessonProgress model (tracks user completion)
4. QuizAttempt model (stores quiz responses)
5. Certificate model (PDF metadata)
6. Conversation model (WhatsApp/USSD state)
7. Employer model (for certificate verification)
8. Analytics model (aggregated KPIs)

Requirements:
- Use SQLAlchemy 2.0 async syntax
- Add proper indexes for foreign keys and frequently queried fields
- Create Alembic migration files
- Nigerian-specific fields: phone_number (10-11 digits), language enum (en, pid, ha, yo, ig)
- NDPA compliance: add consent_given, data_retention_date fields
- After creating models, run migrations and confirm tables exist

Test command:
docker compose exec db psql -U mnair -c "\dt"

Done when: All 8 tables exist in PostgreSQL with proper constraints
```

**What to check**:
- [ ] 8 tables created in database
- [ ] No migration errors
- [ ] Foreign key constraints exist
- [ ] Indexes created on phone_number, language, user_id

---

#### **Session 2: Module 1 — Curriculum Engine**
**Estimated Time**: 3-4 hours

**Prompt to use**:
```
I am building the MNAIR platform. I need Module 1: Curriculum Engine.

CONTEXT (attach these files):
- backend/app/models/lesson.py (from Module 0)
- backend/app/models/lesson_progress.py (from Module 0)

YOUR TASK:
Build the curriculum system:

1. Create 35 YAML lesson files in curriculum/day1/ through curriculum/day7/
   Structure per lesson:
   ```yaml
   id: day1_what_is_ai_en
   day: 1
   topic: what_is_ai
   language: en
   title: "What is AI?"
   content: |
     [Lesson text - max 300 words]
   quiz:
     - question: "..."
       options: [A, B, C, D]
       correct: 0
   ```

2. Write CurriculumLoader service (backend/app/curriculum/loader.py)
   - Load YAML files
   - Validate structure
   - Bulk insert into database
   - Handle duplicates (upsert by id)

3. Create management script to seed database:
   ```bash
   python -m app.curriculum.loader
   ```

Requirements:
- 7 days × 5 topics × 5 languages = 175 lessons total
- Topics: what_is_ai, how_ai_works, ai_in_nigeria, ai_tools, ai_ethics
- Each lesson: 250-300 words, 5 quiz questions
- Nigerian context: Use local examples (Bole festival, Lagos traffic, etc.)
- Pidgin translation must sound natural

Test command:
python -m app.curriculum.loader
python -c "from app.models import Lesson; print(len(Lesson.query.all()))"

Done when: 175 lessons in database, no validation errors
```

**What to check**:
- [ ] 175 YAML files created (35 topics × 5 languages)
- [ ] Loader script runs without errors
- [ ] Database has 175 lesson records
- [ ] Pidgin translations are accurate

---

#### **Session 3: Module 3 — Lesson State Manager**
**Estimated Time**: 2-3 hours

**Prompt to use**:
```
I am building MNAIR. I need Module 3: Lesson State Manager.

CONTEXT (attach):
- backend/app/models/lesson_progress.py
- backend/app/models/quiz_attempt.py
- backend/app/models/lesson.py

YOUR TASK:
Build LessonStateManager service (backend/app/services/lesson_state.py):

Core methods:
1. get_next_lesson(user_id, language) → Lesson
   - Return first incomplete lesson for user's current day
   - If day complete, return None (trigger day completion flow)

2. record_quiz_attempt(user_id, lesson_id, answers) → QuizResult
   - Compare answers to correct answers
   - Calculate score
   - Pass threshold: 3/5 correct (60%)
   - Record attempt in database

3. complete_lesson(user_id, lesson_id) → bool
   - Mark lesson as complete
   - Update completion timestamp
   - Check if day complete (all 5 topics done)

4. is_day_complete(user_id, day) → bool
   - Check if user completed all 5 topics for given day

5. get_user_progress(user_id) → ProgressSummary
   - Return: current_day, lessons_completed, total_lessons, completion_percentage

Requirements:
- Handle quiz retries (max 3 attempts per lesson)
- Lock next day until current day complete
- Use database transactions for consistency
- Write unit tests with pytest

Test command:
pytest tests/test_lesson_state.py -v

Done when: All tests pass, quiz logic works correctly
```

**What to check**:
- [ ] LessonStateManager class created
- [ ] All 5 methods implemented
- [ ] Unit tests pass
- [ ] Quiz retry logic works (max 3 attempts)

---

### 📱 Phase B: Communication Channels

#### **Session 4: Module 2A — WhatsApp Handler**
**Estimated Time**: 4-5 hours (split into 2 conversations if needed)

**Prompt**:
```
I am building MNAIR. I need Module 2A: WhatsApp Handler.

CONTEXT (attach):
- backend/app/services/lesson_state.py (from Module 3)
- backend/app/models/conversation.py (from Module 0)

YOUR TASK:
Build WhatsApp webhook handler (backend/app/channels/whatsapp.py):

1. Webhook endpoint: POST /api/v1/webhooks/whatsapp
   - Verify Meta signature
   - Handle message types: text, interactive button
   - Extract sender phone number, message text

2. Conversation State Machine:
   States:
   - NEW_USER → collect name
   - AWAITING_LANGUAGE → show language buttons
   - IN_LESSON → deliver lesson content
   - AWAITING_QUIZ → handle quiz responses
   - DAY_COMPLETE → congratulate, prompt next day

3. WhatsAppMessageBuilder class:
   - build_welcome_message()
   - build_language_selector()
   - build_lesson_message(lesson)
   - build_quiz_message(quiz)
   - build_day_complete_message(day)

4. Handle full 7-day flow simulation

Requirements:
- Use Meta WhatsApp Business API
- All images <50KB (Nigerian bandwidth)
- Messages <1600 chars (WhatsApp limit)
- Cache frequent messages in Redis
- Track conversation state in DB

Test command:
pytest tests/test_whatsapp_flow.py -v

Done when: Full Day 1-7 conversation simulation passes
```

---

#### **Session 5: Module 2B — USSD Handler**
**Estimated Time**: 2-3 hours

**Prompt**:
```
I am building MNAIR. I need Module 2B: USSD Handler for Africa's Talking.

CONTEXT (attach):
- backend/app/services/lesson_state.py

YOUR TASK:
Build USSD handler (backend/app/channels/ussd.py):

USSD Code: *384*8080#

Menu Flow:
1. Main Menu:
   CON Welcome to Make Nigeria AI Ready
   1. Start Learning
   2. My Progress
   3. Get Certificate

2. Language Selection:
   CON Choose language:
   1. English
   2. Pidgin
   3. Hausa
   4. Yoruba
   5. Igbo

3. Lesson Delivery:
   CON [Lesson content - chunked to 160 chars]
   1. Continue
   0. Main Menu

4. Quiz:
   CON Question 1/5: [question]
   1. [Option A]
   2. [Option B]
   3. [Option C]
   4. [Option D]

Requirements:
- Handle 90-second session timeout
- Chunk long content (160 chars per screen)
- Use CON (continue) and END (terminate) prefixes
- Store session state in Redis (expires in 90s)
- Handle navigation: 0 = back, 00 = main menu

Test command:
Use Africa's Talking USSD simulator

Done when: Can complete full Day 1 via USSD simulation
```

---

### 🔐 Phase C: API & Admin

Continue with Sessions 7-13 following the README.md module plan...

---

## 📝 Tips for Working with Claude

1. **Start each conversation with**:
   - "I am building the MNAIR platform"
   - Module specification
   - Relevant files from previous modules

2. **After each module**:
   - Run the test command
   - Fix any errors before moving on
   - Commit to git with descriptive message

3. **If you hit Claude's context limit**:
   - End conversation
   - Start new conversation with updated context
   - Paste only the files needed for next module

4. **Common issues**:
   - Docker not running → Start Docker Desktop
   - Database connection error → Check `docker compose ps`
   - Import errors → Check __init__.py files exist
   - Test failures → Read error message carefully, fix before proceeding

---

## 🎯 Success Criteria After Phase A

You should have:
- [ ] 8 database tables with data
- [ ] 175 lessons in database (35 topics × 5 languages)
- [ ] LessonStateManager service working
- [ ] All unit tests passing
- [ ] Git commits for each module

---

## 📞 Need Help?

- Docker issues: Check `docker compose logs db`
- Database issues: `docker compose exec db psql -U mnair`
- Python errors: Check virtual environment activated
- Test failures: Run with `-v` flag for verbose output

**Ready to start? Begin with Module 0 (Database Models)!**
