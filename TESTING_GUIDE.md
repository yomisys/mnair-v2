# MNAIR Platform - Step-by-Step Testing Guide

This guide will walk you through testing every major feature of the MNAIR platform.

---

## Prerequisites

Before testing, ensure:
- ✅ Docker services are running (`docker ps` shows 3 mnair containers)
- ✅ Backend API is running (http://localhost:8000/health shows "healthy")
- ✅ Frontend is running (http://localhost:3000 loads)

---

## Test 1: Public Home Page

### Steps:
1. Open your web browser (Chrome, Firefox, or Edge)
2. Navigate to: **http://localhost:3000**
3. You should see the MNAIR home page

### Expected Results:
- ✅ Page loads without errors
- ✅ "Make Nigeria AI Ready" header visible
- ✅ "7-day AI literacy program for all Nigerians" tagline visible
- ✅ Navigation bar with "Home", "Verify Certificate", "Admin Login" buttons
- ✅ Feature cards showing:
  - 5 Nigerian Languages
  - Multiple Channels
  - Just 7 Days
  - Learn by Doing
  - Earn Certificate
  - 100% Free
- ✅ Curriculum overview showing 7-day program
- ✅ Statistics section (175 Lessons, 5 Languages, 7 Days, Free)
- ✅ Footer with contact information

### What to Check:
- [ ] All images/icons load correctly
- [ ] All buttons are clickable
- [ ] Page is responsive (try resizing browser window)
- [ ] No JavaScript errors in browser console (F12 → Console tab)

### Screenshot Location:
Take a screenshot and save as: `screenshots/01_home_page.png`

---

## Test 2: Certificate Verification Page

### Steps:
1. From the home page, click **"Verify Certificate"** in the navigation bar
2. OR navigate directly to: **http://localhost:3000/verify**

### Expected Results:
- ✅ "Verify Certificate" page loads
- ✅ Input field with label "Certificate ID"
- ✅ Placeholder text shows format: "MNAIR-2024-00123-A7B9C2"
- ✅ "Verify Certificate" button visible

### Test Invalid Certificate:
1. Enter a fake certificate ID: `MNAIR-2024-00000-TEST123`
2. Click **"Verify Certificate"**
3. Expected: Red error alert appears: "Certificate not found. Please check the ID and try again."

### Test Empty Input:
1. Leave the input field empty
2. Try clicking **"Verify Certificate"**
3. Expected: Button is disabled or browser shows "Please fill out this field"

### What to Check:
- [ ] Input field accepts text
- [ ] Button shows loading state when clicked
- [ ] Error message displays correctly
- [ ] Can navigate back to home page

### Screenshot Location:
Take screenshots:
- `screenshots/02_verify_page.png`
- `screenshots/02_verify_error.png`

---

## Test 3: Admin Login

### Steps:
1. Navigate to: **http://localhost:3000/login**
2. You should see the login page

### Expected Results:
- ✅ "Login" or "MNAIR Admin Login" header
- ✅ Phone number input field
- ✅ Password input field
- ✅ "Login" button

### Test Login with Correct Credentials:

#### Step 3.1: Enter Credentials
1. **Phone Number**: `+2348000000000`
2. **Password**: `admin123`
3. Click **"Login"** button

#### Step 3.2: Verify Login Success
Expected Results:
- ✅ Button shows loading state briefly
- ✅ Page redirects to dashboard: **http://localhost:3000/dashboard**
- ✅ No error messages

### Test Login with Wrong Credentials:

#### Step 3.3: Logout (if logged in)
1. If you're on the dashboard, look for a "Logout" button in the top navigation
2. Click **"Logout"**
3. You should be redirected back to login or home page

#### Step 3.4: Try Wrong Password
1. Navigate to: **http://localhost:3000/login**
2. Phone Number: `+2348000000000`
3. Password: `wrongpassword`
4. Click **"Login"**
5. Expected: Error message appears (e.g., "Invalid credentials" or "Login failed")

### What to Check:
- [ ] Input fields accept text
- [ ] Password field shows dots/asterisks (hidden text)
- [ ] Login button shows loading state
- [ ] Error messages display correctly
- [ ] Successful login redirects to dashboard

### Screenshot Location:
Take screenshots:
- `screenshots/03_login_page.png`
- `screenshots/03_login_error.png`
- `screenshots/03_login_success_redirect.png`

---

## Test 4: Admin Dashboard

### Prerequisites:
- You must be logged in as admin (complete Test 3 first)

### Steps:
1. After successful login, you should be at: **http://localhost:3000/dashboard**

### Expected Results:
- ✅ Dashboard page loads
- ✅ Navigation bar shows:
  - "MNAIR Admin" branding
  - User name and role: "MNAIR Administrator (admin)"
  - "Logout" button
- ✅ Dashboard content displays (will vary based on implementation)

### Common Dashboard Features to Check:

#### 4.1 Overview/Statistics Section
Look for cards or sections showing:
- [ ] Total Users count
- [ ] Total Lessons (should show 175)
- [ ] Active Learners
- [ ] Certificates Issued
- [ ] Completion Rate

#### 4.2 Navigation/Tabs
Check if dashboard has tabs or sidebar menu for:
- [ ] Overview/Home
- [ ] Users Management
- [ ] Lessons Management
- [ ] Analytics
- [ ] Certificates
- [ ] Employers
- [ ] Settings

#### 4.3 Data Tables
If there are tables showing users, lessons, etc.:
- [ ] Table displays data
- [ ] Columns are properly labeled
- [ ] Pagination works (if applicable)
- [ ] Search/filter works (if applicable)

### What to Check:
- [ ] All dashboard sections load without errors
- [ ] Numbers/statistics display correctly
- [ ] Navigation between dashboard sections works
- [ ] "Logout" button works and returns to home/login page
- [ ] No JavaScript errors in console

### Screenshot Location:
Take screenshots:
- `screenshots/04_dashboard_overview.png`
- `screenshots/04_dashboard_users.png` (if user management exists)
- `screenshots/04_dashboard_lessons.png` (if lesson management exists)

---

## Test 5: Backend API Endpoints

### Test 5.1: API Documentation

#### Steps:
1. Open a new browser tab
2. Navigate to: **http://localhost:8000/docs**

#### Expected Results:
- ✅ Swagger UI loads
- ✅ Lists all available API endpoints organized by category:
  - Authentication
  - Lessons
  - Certificates
  - Analytics
  - Employers
- ✅ Each endpoint shows HTTP method (GET, POST, PUT, DELETE)

#### What to Check:
- [ ] Page loads without errors
- [ ] Can expand/collapse endpoint groups
- [ ] Click on an endpoint shows request/response details
- [ ] "Try it out" button is available

### Test 5.2: Health Check Endpoint

#### Using Browser:
1. Navigate to: **http://localhost:8000/health**

#### Expected Results:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "minio": "connected"
}
```

#### Using Command Line (Optional):
```bash
curl http://localhost:8000/health
```

### Test 5.3: Root Endpoint

#### Steps:
1. Navigate to: **http://localhost:8000/**

#### Expected Results:
```json
{
  "name": "Make Nigeria AI Ready",
  "version": "v1",
  "status": "healthy",
  "environment": "development"
}
```

### Test 5.4: Get Lessons (via Swagger UI)

#### Steps:
1. Go to: **http://localhost:8000/docs**
2. Find the **Lessons** section
3. Look for `GET /api/v1/lessons` endpoint
4. Click to expand it
5. Click **"Try it out"** button
6. Click **"Execute"** button

#### Expected Results:
- ✅ Response code: 200
- ✅ Response body shows array of lessons
- ✅ Each lesson has fields: id, day, topic, language, title, content, quiz

#### Sample Response:
```json
[
  {
    "id": 1,
    "lesson_id": "day1_what_is_ai_en",
    "day": 1,
    "topic": "what_is_ai",
    "language": "en",
    "title": "What is AI?",
    "content": "...",
    "quiz": {...}
  }
]
```

### Screenshot Location:
Take screenshots:
- `screenshots/05_api_docs.png`
- `screenshots/05_api_health.png`
- `screenshots/05_api_lessons.png`

---

## Test 6: Database Verification

### Test 6.1: Check Lessons Count

#### Using Command Line:
```bash
cd /c/Users/yomis/mnair/backend

./venv/Scripts/python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models.lesson import Lesson
from sqlalchemy import select, func

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count(Lesson.id)))
        count = result.scalar()
        print(f'Total lessons: {count}')

        # By language
        result = await db.execute(
            select(Lesson.language, func.count(Lesson.id))
            .group_by(Lesson.language)
        )
        print('\nBy language:')
        for lang, count in result:
            print(f'  {lang}: {count}')

asyncio.run(check())
"
```

#### Expected Output:
```
Total lessons: 175

By language:
  en: 35
  ha: 35
  ig: 35
  pid: 35
  yo: 35
```

### Test 6.2: Check Admin User

#### Using Command Line:
```bash
cd /c/Users/yomis/mnair/backend

./venv/Scripts/python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.phone_number == '+2348000000000')
        )
        user = result.scalar_one_or_none()
        if user:
            print(f'Admin user found:')
            print(f'  Name: {user.name}')
            print(f'  Phone: {user.phone_number}')
            print(f'  Role: {user.role}')
            print(f'  Active: {user.is_active}')
        else:
            print('Admin user not found!')

asyncio.run(check())
"
```

#### Expected Output:
```
Admin user found:
  Name: MNAIR Administrator
  Phone: +2348000000000
  Role: UserRole.ADMIN
  Active: True
```

---

## Test 7: Docker Services

### Test 7.1: Check All Containers

#### Command:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

#### Expected Output:
```
NAMES            STATUS                     PORTS
mnair_postgres   Up X hours (healthy)       0.0.0.0:5433->5432/tcp
mnair_redis      Up X hours (healthy)       0.0.0.0:6380->6379/tcp
mnair_minio      Up X hours (healthy)       0.0.0.0:9000-9001->9000-9001/tcp
```

### Test 7.2: PostgreSQL Connection

#### Command:
```bash
docker exec mnair_postgres pg_isready -U postgres
```

#### Expected Output:
```
/var/run/postgresql:5432 - accepting connections
```

### Test 7.3: Redis Connection

#### Command:
```bash
docker exec mnair_redis redis-cli ping
```

#### Expected Output:
```
PONG
```

### Test 7.4: MinIO Console

#### Steps:
1. Open browser and navigate to: **http://localhost:9001**
2. Login page should appear

---

## Test 8: Error Handling

### Test 8.1: Backend API - Invalid Endpoint

#### Steps:
1. Navigate to: **http://localhost:8000/api/v1/invalid-endpoint**

#### Expected Results:
- ✅ Response code: 404
- ✅ JSON response with error message

### Test 8.2: Frontend - Invalid Route

#### Steps:
1. Navigate to: **http://localhost:3000/invalid-page**

#### Expected Results:
- ✅ Either shows 404 page or redirects to home
- ✅ No blank white page

---

## Test 9: Browser Console Check

### Steps:
1. Open any page of the frontend (home, verify, login, or dashboard)
2. Press **F12** to open Developer Tools
3. Go to **Console** tab

### Expected Results:
- ✅ No red error messages
- ✅ May see blue/gray info messages (these are OK)
- ✅ No "CORS" errors
- ✅ No "Failed to load resource" errors

### Common Issues:
- **CORS errors**: Check backend CORS configuration
- **404 errors**: Check API endpoint URLs
- **Network errors**: Check if backend is running

---

## Test 10: Complete User Flow Test

### Scenario: Admin Reviews Platform Statistics

#### Steps:
1. **Start at Home Page**: http://localhost:3000
   - ✅ Page loads successfully

2. **Navigate to Login**: Click "Admin Login" button
   - ✅ Redirects to login page

3. **Login**:
   - Phone: `+2348000000000`
   - Password: `admin123`
   - Click "Login"
   - ✅ Successfully logs in

4. **View Dashboard**:
   - ✅ Dashboard loads with statistics
   - ✅ Can see lesson count (175)
   - ✅ Navigation works

5. **Check API Documentation**:
   - Open new tab: http://localhost:8000/docs
   - ✅ Swagger UI loads

6. **Verify Certificate Page**:
   - Navigate to: http://localhost:3000/verify
   - ✅ Still logged in (see logout button)
   - ✅ Verify page works

7. **Logout**:
   - Click "Logout" button
   - ✅ Redirects to home/login page
   - ✅ Cannot access dashboard anymore

---

## Troubleshooting Common Issues

### Issue 1: Backend API not responding
**Symptoms**: Can't access http://localhost:8000

**Solutions**:
1. Check if backend is running: Look for the terminal window running uvicorn
2. Check port 8000 is not used by another app:
   ```bash
   netstat -ano | findstr :8000
   ```
3. Restart backend:
   ```bash
   cd /c/Users/yomis/mnair/backend
   ./venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

### Issue 2: Frontend not loading
**Symptoms**: Can't access http://localhost:3000

**Solutions**:
1. Check if frontend is running: Look for terminal with "VITE" output
2. Check port 3000 is available
3. Restart frontend:
   ```bash
   cd /c/Users/yomis/mnair/frontend
   npm run dev
   ```

### Issue 3: Login fails
**Symptoms**: "Invalid credentials" or "Login failed"

**Solutions**:
1. Verify admin user exists:
   ```bash
   cd /c/Users/yomis/mnair/backend
   ./venv/Scripts/python create_admin.py
   ```
2. Check browser console for errors (F12)
3. Verify backend is running and healthy: http://localhost:8000/health

### Issue 4: No lessons showing
**Symptoms**: Lesson endpoints return empty array

**Solutions**:
1. Check if lessons are loaded:
   ```bash
   cd /c/Users/yomis/mnair/backend
   ./venv/Scripts/python load_curriculum.py
   ```
2. Should show "Successfully loaded X lessons" or "Skipped 175 existing lessons"

### Issue 5: Docker services not running
**Symptoms**: Health check shows "database: disconnected"

**Solutions**:
```bash
# Check containers
docker ps

# If not running, start them
cd /c/Users/yomis/mnair
docker-compose up -d

# Check logs
docker logs mnair_postgres
docker logs mnair_redis
docker logs mnair_minio
```

---

## Testing Checklist

Use this checklist to track your testing progress:

### Public Features
- [ ] Home page loads correctly
- [ ] All sections visible (hero, features, curriculum, stats, CTA)
- [ ] Navigation works
- [ ] Footer displays correctly
- [ ] Certificate verification page loads
- [ ] Certificate verification handles invalid input

### Admin Features
- [ ] Login page loads
- [ ] Login works with correct credentials
- [ ] Login rejects wrong credentials
- [ ] Dashboard loads after login
- [ ] Dashboard shows statistics
- [ ] Logout works correctly
- [ ] Protected routes require authentication

### API Features
- [ ] API documentation loads (Swagger UI)
- [ ] Health check endpoint works
- [ ] Root endpoint returns correct info
- [ ] Lessons endpoint returns data
- [ ] API handles invalid endpoints gracefully

### Infrastructure
- [ ] PostgreSQL container running and healthy
- [ ] Redis container running and healthy
- [ ] MinIO container running and healthy
- [ ] Database has 175 lessons
- [ ] Admin user exists in database

### Error Handling
- [ ] No console errors on any page
- [ ] Invalid routes handled gracefully
- [ ] Network errors shown to user
- [ ] Form validation works

---

## Reporting Issues

If you find any issues during testing:

1. **Note the Issue**:
   - What page/feature?
   - What did you do?
   - What happened?
   - What should have happened?

2. **Check Browser Console**:
   - Press F12
   - Look for red errors
   - Copy error messages

3. **Check Backend Logs**:
   - Look at uvicorn terminal output
   - Note any error messages

4. **Take Screenshots**:
   - Save in `screenshots/` folder
   - Name with issue description

---

## Next Steps After Testing

Once all tests pass:

1. **Document any issues found**
2. **Take screenshots of successful tests**
3. **Review `DEPLOYMENT_GUIDE.md` for production deployment**
4. **Plan production environment setup**
5. **Schedule user acceptance testing**

---

**Happy Testing!** 🚀

If you encounter any issues not covered in this guide, check:
- `QUICK_START.md` - Common operations
- `DEPLOYMENT_STATUS.md` - Current platform status
- `README.md` - Project overview
