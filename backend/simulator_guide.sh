#!/bin/bash

# WhatsApp Simulator Step-by-Step Guide
# ======================================

BASE_URL="http://localhost:8000/api/v1/test/whatsapp"
PHONE="+2348100000001"  # Use your own test number

echo "========================================"
echo "WhatsApp Simulator - Step by Step Guide"
echo "========================================"
echo ""
echo "Testing with phone: $PHONE"
echo ""

# STEP 1: Start conversation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Send START to begin"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Command:"
echo "curl -X POST \"$BASE_URL/simulate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"phone_number\":\"$PHONE\",\"message\":\"START\"}'"
echo ""
echo "Response:"

response=$(curl -s -X POST "$BASE_URL/simulate" \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"START\"}")

echo "$response" | python -m json.tool 2>/dev/null | head -30

echo ""
echo "What happened:"
echo "✓ New user created"
echo "✓ Welcome message sent"
echo "✓ Language selector displayed"
echo ""
read -p "Press Enter to continue to Step 2..."

# STEP 2: Select language
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Select English language"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Available language options:"
echo "  - lang_en (English)"
echo "  - lang_pid (Pidgin)"
echo "  - lang_ha (Hausa)"
echo "  - lang_yo (Yoruba)"
echo "  - lang_ig (Igbo)"
echo ""
echo "Command:"
echo "curl -X POST \"$BASE_URL/simulate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"phone_number\":\"$PHONE\",\"message\":\"lang_en\"}'"
echo ""
echo "Response (first 40 lines):"

response=$(curl -s -X POST "$BASE_URL/simulate" \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"lang_en\"}")

echo "$response" | python -m json.tool 2>/dev/null | head -40

echo ""
echo "What happened:"
echo "✓ Language set to English"
echo "✓ First lesson delivered (Day 1, Lesson 1)"
echo "✓ User can now start quiz"
echo ""
read -p "Press Enter to continue to Step 3..."

# STEP 3: Start quiz
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Start the quiz"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Command:"
echo "curl -X POST \"$BASE_URL/simulate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"phone_number\":\"$PHONE\",\"message\":\"QUIZ\"}'"
echo ""
echo "Response (first 30 lines):"

response=$(curl -s -X POST "$BASE_URL/simulate" \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"QUIZ\"}")

echo "$response" | python -m json.tool 2>/dev/null | head -30

echo ""
echo "What happened:"
echo "✓ Quiz started for Lesson 1"
echo "✓ First question displayed with 4 options"
echo "✓ User can select answer"
echo ""
read -p "Press Enter to continue to Step 4..."

# STEP 4: Answer question
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Answer the question"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Answer format: ans_QUESTION_OPTION"
echo "  - ans_0_0 = Question 0, Option A"
echo "  - ans_0_1 = Question 0, Option B"
echo "  - ans_0_2 = Question 0, Option C"
echo "  - ans_0_3 = Question 0, Option D"
echo ""
echo "Command (answering with Option B):"
echo "curl -X POST \"$BASE_URL/simulate\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"phone_number\":\"$PHONE\",\"message\":\"ans_0_1\"}'"
echo ""
echo "Response (first 30 lines):"

response=$(curl -s -X POST "$BASE_URL/simulate" \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_0_1\"}")

echo "$response" | python -m json.tool 2>/dev/null | head -30

echo ""
echo "What happened:"
echo "✓ Answer recorded"
echo "✓ Next question displayed (Question 2/5)"
echo "✓ Progress tracked"
echo ""
read -p "Press Enter to continue to Step 5..."

# STEP 5: Check user state
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5: Check current user state"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Command:"
echo "curl -X GET \"$BASE_URL/user/$PHONE\""
echo ""
echo "Response:"

curl -s -X GET "$BASE_URL/user/$PHONE" | python -m json.tool

echo ""
echo "What the state shows:"
echo "✓ user_id - Unique user identifier"
echo "✓ current_day - What day they're on (1-7)"
echo "✓ language - Selected language"
echo "✓ conversation_state - Current state in flow"
echo "✓ context - Current lesson, question, answers"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Guide Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps to complete the quiz:"
echo "  1. Answer remaining 4 questions:"
echo "     ans_1_2 (Question 2, Option C)"
echo "     ans_2_1 (Question 3, Option B)"
echo "     ans_3_2 (Question 4, Option C)"
echo "     ans_4_1 (Question 5, Option B)"
echo ""
echo "  2. Get next lesson with: message=\"NEXT\""
echo ""
echo "  3. Repeat for 5 lessons per day"
echo ""
echo "  4. Complete 7 days for certificate"
echo ""
echo "Test endpoints:"
echo "  - POST $BASE_URL/simulate"
echo "  - GET  $BASE_URL/user/{phone_number}"
echo ""
