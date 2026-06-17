#!/bin/bash
PHONE="+2348123456789"
URL="http://localhost:8000/api/v1/test/whatsapp"

echo "=== WhatsApp Simulator Quick Test ==="
echo "Phone: $PHONE"
echo ""

# Answer remaining questions
echo ">> Answering Question 2 (Option C)"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_1_2\"}" > /dev/null

echo ">> Answering Question 3 (Option B)"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_2_1\"}" > /dev/null

echo ">> Answering Question 4 (Option C)"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_3_2\"}" > /dev/null

echo ">> Answering Question 5 (Option B)"
response=$(curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"ans_4_1\"}")

echo ""
echo "=== Quiz Complete! ==="
echo ""
echo "Final State:"
curl -s -X GET "$URL/user/$PHONE" | python -m json.tool
