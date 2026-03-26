#!/bin/bash
###############################################################################
# WhatsApp Learning Journey - Complete 7-Day Test
# Tests the full MNAIR AI literacy program through WhatsApp simulator
###############################################################################

BASE_URL="http://localhost:8000/api/v1/test/whatsapp"
PHONE="+2349012345678"

# Color codes for output (if supported)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=============================================="
echo "WhatsApp Learning Journey - 7-Day Test"
echo "=============================================="
echo ""
echo "Phone: $PHONE"
echo "Testing complete MNAIR program"
echo ""

# Function to send message and extract info
send_msg() {
    local msg="$1"
    local desc="$2"

    echo ">> $desc"
    echo "   Sending: $msg"

    response=$(curl -s -X POST "$BASE_URL/simulate" \
        -H "Content-Type: application/json" \
        -d "{\"phone_number\":\"$PHONE\",\"message\":\"$msg\"}")

    if [ $? -eq 0 ]; then
        state=$(echo "$response" | grep -o '"conversation_state":"[^"]*"' | cut -d'"' -f4)
        day=$(echo "$response" | grep -o '"current_day":[0-9]*' | cut -d':' -f2)
        echo "   Status: OK | State: $state | Day: $day"
    else
        echo "   Status: ERROR"
    fi
    echo ""
    sleep 0.5
}

# Function to complete a quiz (answer all 5 questions)
complete_quiz() {
    local lesson_num=$1
    echo ""
    echo "=== QUIZ for Lesson $lesson_num ==="

    # Start quiz
    send_msg "QUIZ" "Starting quiz"

    # Answer 5 questions with mixed correct answers
    # Using pattern: B, C, B, C, B (typically correct)
    send_msg "ans_0_1" "Q1: Answer B"
    send_msg "ans_1_2" "Q2: Answer C"
    send_msg "ans_2_1" "Q3: Answer B"
    send_msg "ans_3_2" "Q4: Answer C"
    send_msg "ans_4_1" "Q5: Answer B"

    echo "=== Quiz Complete ==="
    echo ""
}

# Function to complete a full day (5 lessons)
complete_day() {
    local day_num=$1
    echo ""
    echo "######################################"
    echo "#  DAY $day_num - 5 LESSONS"
    echo "######################################"
    echo ""

    for lesson in {1..5}; do
        echo "--- Lesson $lesson/5 ---"

        # First lesson of day 1 is already delivered after language selection
        if [ $day_num -eq 1 ] && [ $lesson -eq 1 ]; then
            echo "   (First lesson already delivered)"
        else
            send_msg "NEXT" "Get Lesson $lesson"
        fi

        # Complete the quiz
        complete_quiz $lesson

        sleep 1
    done

    echo "DAY $day_num COMPLETE!"
    echo ""
}

# START THE JOURNEY
echo "=============================================="
echo "PHASE 1: ONBOARDING"
echo "=============================================="
echo ""

send_msg "START" "1. Start conversation"
sleep 1

send_msg "lang_en" "2. Select English language"
sleep 1

echo ""
echo "=============================================="
echo "PHASE 2: 7-DAY LEARNING JOURNEY"
echo "=============================================="
echo ""

# Complete all 7 days
for day in {1..7}; do
    complete_day $day

    # After completing a day (except last), advance to next day
    if [ $day -lt 7 ]; then
        echo ">>> Advancing to Day $((day+1))..."
        send_msg "NEXT" "Advance to Day $((day+1))"
        sleep 2
    fi
done

echo ""
echo "=============================================="
echo "PHASE 3: COMPLETION & CERTIFICATE"
echo "=============================================="
echo ""

# Check final state
echo "Checking final user state..."
final_state=$(curl -s -X GET "$BASE_URL/user/$PHONE")

echo ""
echo "FINAL STATE:"
echo "$final_state" | python -m json.tool 2>/dev/null || echo "$final_state"

echo ""
echo "=============================================="
echo "JOURNEY COMPLETE!"
echo "=============================================="
echo ""
echo "Summary:"
echo "  - 7 days completed"
echo "  - 35 lessons delivered (5 per day)"
echo "  - 175 quiz questions answered (5 per lesson)"
echo "  - User eligible for certificate"
echo ""
echo "Next steps:"
echo "  1. Check certificate generation"
echo "  2. Test certificate verification"
echo "  3. View analytics dashboard"
echo ""
