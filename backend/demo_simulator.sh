#!/bin/bash
PHONE="+2349999888877"
URL="http://localhost:8000/api/v1/test/whatsapp"

echo "=========================================="
echo "WhatsApp Simulator Demo"
echo "=========================================="
echo "Phone: $PHONE"
echo ""

echo "STEP 1: Send START"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"START\"}" | python -m json.tool | head -15
echo ""

sleep 1

echo "STEP 2: Select English (lang_en)"
curl -s -X POST "$URL/simulate" -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"$PHONE\",\"message\":\"lang_en\"}" | python -m json.tool | head -20
echo ""

sleep 1

echo "STEP 3: Check User State"
curl -s -X GET "$URL/user/$PHONE" | python -m json.tool
