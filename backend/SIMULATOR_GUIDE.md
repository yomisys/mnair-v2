# WhatsApp Simulator - Step-by-Step Testing Guide

## Prerequisites
- Backend server running on `http://localhost:8000`
- Test phone number (e.g., `+2348100000001`)

## Base URL
```
http://localhost:8000/api/v1/test/whatsapp
```

---

## STEP 1: Start Conversation

Send "START" to create a new user and receive welcome message.

**Command:**
```bash
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"START"}'
```

**What Happens:**
- ✓ New user created with unique ID
- ✓ Welcome message sent
- ✓ Language selector displayed
- ✓ State: `awaiting_language`

**Response Example:**
```json
{
  "status": "success",
  "user_id": 9,
  "user_name": "WhatsApp User",
  "conversation_state": "awaiting_language",
  "messages_sent": [
    {
      "to": "+2348100000001",
      "message": {
        "type": "text",
        "text": {
          "body": "Hello! Welcome to MNAIR..."
        }
      }
    }
  ]
}
```

---

## STEP 2: Select Language

Choose preferred language for learning.

**Available Options:**
- `lang_en` - English
- `lang_pid` - Nigerian Pidgin
- `lang_ha` - Hausa
- `lang_yo` - Yoruba
- `lang_ig` - Igbo

**Command:**
```bash
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"lang_en"}'
```

**What Happens:**
- ✓ Language set to English
- ✓ First lesson delivered (Day 1, Lesson 1)
- ✓ Lesson content sent with Nigerian context
- ✓ State: `in_lesson`

**Response Contains:**
- Full lesson text about "AI Ethics and Responsibility"
- Instructions to start quiz

---

## STEP 3: Start Quiz

Begin the quiz after reading the lesson.

**Command:**
```bash
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"QUIZ"}'
```

**What Happens:**
- ✓ Quiz started for current lesson
- ✓ First question (1/5) displayed
- ✓ 4 multiple choice options shown
- ✓ State: `awaiting_quiz`

---

## STEP 4: Answer Questions

Answer each of the 5 quiz questions.

**Answer Format:**
```
ans_QUESTION_OPTION
```

Where:
- `QUESTION` = Question number (0-4)
- `OPTION` = Option number (0-3 for A-D)

**Examples:**
- `ans_0_0` = Question 1, Option A
- `ans_0_1` = Question 1, Option B
- `ans_0_2` = Question 1, Option C
- `ans_0_3` = Question 1, Option D

**Command (Answer Question 1):**
```bash
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_0_1"}'
```

**Complete Quiz (All 5 Questions):**
```bash
# Question 1 - Option B
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_0_1"}'

# Question 2 - Option C
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_1_2"}'

# Question 3 - Option B
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_2_1"}'

# Question 4 - Option C
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_3_2"}'

# Question 5 - Option B
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"ans_4_1"}'
```

**What Happens:**
- ✓ Each answer is recorded
- ✓ Next question displayed after each answer
- ✓ After question 5, quiz results shown
- ✓ State changes based on quiz performance

---

## STEP 5: Check User State

View current progress anytime.

**Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/test/whatsapp/user/+2348100000001"
```

**Response:**
```json
{
  "user_id": 9,
  "name": "WhatsApp User",
  "phone_number": "+2348100000001",
  "language": "en",
  "current_day": 1,
  "conversation_state": "in_lesson",
  "context": {
    "current_lesson_id": 1,
    "current_question": 2,
    "answers": [1, 2]
  },
  "is_active": true
}
```

**State Fields:**
- `user_id` - Unique identifier
- `current_day` - Current day (1-7)
- `language` - Selected language
- `conversation_state` - Current state in flow
- `context.current_lesson_id` - Current lesson ID
- `context.current_question` - Current quiz question
- `context.answers` - Quiz answers given

---

## STEP 6: Get Next Lesson

After completing a quiz, request the next lesson.

**Command:**
```bash
curl -X POST "http://localhost:8000/api/v1/test/whatsapp/simulate" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+2348100000001","message":"NEXT"}'
```

**What Happens:**
- ✓ Next lesson delivered (Lesson 2/5)
- ✓ New lesson content sent
- ✓ Ready to start next quiz

---

## Complete Flow Summary

### One Day (5 Lessons)

```bash
PHONE="+2348100000001"
URL="http://localhost:8000/api/v1/test/whatsapp"

# Day starts
curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"START\"}"

curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"lang_en\"}"

# For each of 5 lessons:
for lesson in {1..5}; do
  # Get lesson (first lesson already delivered)
  if [ $lesson -gt 1 ]; then
    curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
      -d "{\"phone_number\":\"$PHONE\",\"message\":\"NEXT\"}"
  fi
  
  # Start quiz
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"QUIZ\"}"
  
  # Answer 5 questions
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_0_1\"}"
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_1_2\"}"
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_2_1\"}"
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_3_2\"}"
  curl -X POST "$URL/simulate" -H "Content-Type: application/json" \
    -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_4_1\"}"
done
```

---

## Conversation States

| State | Description |
|-------|-------------|
| `new_user` | Just created, needs welcome |
| `awaiting_language` | Waiting for language selection |
| `in_lesson` | Lesson delivered, can start quiz |
| `awaiting_quiz` | In quiz, answering questions |
| `day_complete` | Finished 5 lessons for the day |
| `program_complete` | Finished all 7 days |

---

## Quick Reference

### Endpoints
```
POST /api/v1/test/whatsapp/simulate    - Send message
GET  /api/v1/test/whatsapp/user/{phone} - Get user state
```

### Message Types
```
START         - Start learning
lang_en       - Select English
lang_pid      - Select Pidgin
lang_ha       - Select Hausa
lang_yo       - Select Yoruba
lang_ig       - Select Igbo
QUIZ          - Start quiz
ans_Q_O       - Answer question (Q=0-4, O=0-3)
NEXT          - Get next lesson
```

### Testing Tips
1. Use unique phone numbers for each test (+234810000000X)
2. Check user state frequently to track progress
3. Quiz requires 60% pass rate (3/5 correct)
4. Complete 5 lessons per day
5. Complete 7 days for certificate

---

## Automated Testing

For complete 7-day journey:
```bash
cd C:/Users/yomis/mnair/backend
bash test_journey.sh
```

For interactive testing:
```bash
cd C:/Users/yomis/mnair/backend
python test_full_journey.py
```

