#!/bin/bash
PHONE="+234810TEST001"
URL="http://localhost:8000/api/v1/test/whatsapp"

echo "=========================================="
echo "Quick Live Test - WhatsApp Simulator"
echo "=========================================="
echo "Phone: $PHONE"
echo ""

echo "1. START"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"START\"}" | python -m json.tool | grep -E "(status|user_id|conversation_state)" | head -3

echo ""
echo "2. SELECT ENGLISH"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"lang_en\"}" | python -m json.tool | grep -E "(status|conversation_state)" | head -2

echo ""
echo "3. START QUIZ"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"QUIZ\"}" | python -m json.tool | grep -E "(status|conversation_state)" | head -2

echo ""
echo "4. USER STATE"
curl -s -X GET "$URL/user/$PHONE" | python -m json.tool

echo ""
echo "=========================================="
echo "✅ Simulator is working!"
echo "=========================================="
