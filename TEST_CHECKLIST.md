# MNAIR Platform - Quick Test Checklist

Print this page or keep it open while testing!

---

## 🚀 Quick Start

**Before You Begin:**
1. [ ] Backend running at http://localhost:8000
2. [ ] Frontend running at http://localhost:3000
3. [ ] Docker services running (`docker ps` shows 3 mnair containers)

---

## ✅ 10-Minute Quick Test

### Test 1: Home Page (2 minutes)
```
URL: http://localhost:3000
```
- [ ] Page loads without errors
- [ ] "Make Nigeria AI Ready" header visible
- [ ] Navigation bar works
- [ ] Footer displays
- [ ] No console errors (F12)

**✓ PASS** | **✗ FAIL** (if fail, see TESTING_GUIDE.md Test 1)

---

### Test 2: Certificate Verification (2 minutes)
```
URL: http://localhost:3000/verify
```
- [ ] Verify page loads
- [ ] Enter: `MNAIR-2024-00000-TEST123`
- [ ] Click "Verify Certificate"
- [ ] Error message appears: "Certificate not found"

**✓ PASS** | **✗ FAIL** (if fail, see TESTING_GUIDE.md Test 2)

---

### Test 3: Admin Login (2 minutes)
```
URL: http://localhost:3000/login
Credentials: +2348000000000 / admin123
```
- [ ] Login page loads
- [ ] Enter phone: `+2348000000000`
- [ ] Enter password: `admin123`
- [ ] Click "Login"
- [ ] Redirects to dashboard

**✓ PASS** | **✗ FAIL** (if fail, see TESTING_GUIDE.md Test 3)

---

### Test 4: Dashboard (2 minutes)
```
URL: http://localhost:3000/dashboard
(Must be logged in)
```
- [ ] Dashboard loads
- [ ] User name shows: "MNAIR Administrator (admin)"
- [ ] Statistics/data displays
- [ ] Logout button works

**✓ PASS** | **✗ FAIL** (if fail, see TESTING_GUIDE.md Test 4)

---

### Test 5: API Documentation (2 minutes)
```
URL: http://localhost:8000/docs
```
- [ ] Swagger UI loads
- [ ] Shows API endpoints
- [ ] Can expand endpoint groups
- [ ] "Try it out" button available

**✓ PASS** | **✗ FAIL** (if fail, see TESTING_GUIDE.md Test 5)

---

## 🔍 Detailed Tests (Optional)

### Database Tests
```bash
cd /c/Users/yomis/mnair/backend
```

**Check Lessons:**
```bash
./venv/Scripts/python -c "import asyncio; from app.database import AsyncSessionLocal; from app.models.lesson import Lesson; from sqlalchemy import select, func; asyncio.run((lambda: AsyncSessionLocal().__aenter__()).__await__())"
```

- [ ] 175 lessons total
- [ ] 35 lessons per language (en, ha, ig, pid, yo)

**Check Admin User:**
```bash
./venv/Scripts/python create_admin.py
```

- [ ] Admin user exists or created

---

### Docker Services
```bash
docker ps
```

- [ ] mnair_postgres - Healthy
- [ ] mnair_redis - Healthy
- [ ] mnair_minio - Healthy

---

### API Health Check
```bash
curl http://localhost:8000/health
```

Expected Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "minio": "connected"
}
```

- [ ] All services show "connected"

---

## 🐛 Troubleshooting

### If Backend Not Responding:
```bash
cd /c/Users/yomis/mnair/backend
./venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### If Frontend Not Loading:
```bash
cd /c/Users/yomis/mnair/frontend
npm run dev
```

### If Docker Services Down:
```bash
cd /c/Users/yomis/mnair
docker-compose up -d
```

### Check Logs:
- Backend: Check uvicorn terminal output
- Frontend: Check vite terminal output
- Docker: `docker logs mnair_postgres`

---

## 📊 Test Summary

**Date:** _______________

**Tester:** _______________

| Test | Status | Notes |
|------|--------|-------|
| Home Page | ☐ Pass ☐ Fail | |
| Certificate Verify | ☐ Pass ☐ Fail | |
| Admin Login | ☐ Pass ☐ Fail | |
| Dashboard | ☐ Pass ☐ Fail | |
| API Docs | ☐ Pass ☐ Fail | |
| Database (175 lessons) | ☐ Pass ☐ Fail | |
| Docker Services | ☐ Pass ☐ Fail | |
| API Health | ☐ Pass ☐ Fail | |

**Overall Status:** ☐ All Tests Passed ☐ Some Tests Failed

---

## 📝 Issues Found

Use this space to note any issues:

1. _______________________________________________________________

2. _______________________________________________________________

3. _______________________________________________________________

---

## ✨ Next Steps

After all tests pass:

- [ ] Review TESTING_GUIDE.md for comprehensive testing
- [ ] Take screenshots of key pages
- [ ] Review DEPLOYMENT_GUIDE.md for production deployment
- [ ] Plan user acceptance testing (UAT)
- [ ] Update documentation with any findings

---

**For detailed testing instructions, see: TESTING_GUIDE.md**

**For troubleshooting, see: QUICK_START.md**
